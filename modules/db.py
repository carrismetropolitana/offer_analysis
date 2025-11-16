from pymongo import MongoClient
import pandas as pd
import config


def load_data(start_date: str, end_date: str, line_ids: list[int] = None) -> pd.DataFrame:
    """
    Query MongoDB and return rides dataframe.

    Parameters
    ----------
    start_date : str (YYYYMMDD)
    end_date : str (YYYYMMDD)
    line_ids : list[int]
        Optional list of line_ids to filter.

    Returns
    -------
    pd.DataFrame
    """
    client = MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]
    collection = db[config.COLLECTION_NAME]

    match_stage = {
        "operational_date": {"$gte": start_date, "$lte": end_date}
    }
    if line_ids:
        match_stage["line_id"] = {"$in": line_ids}

    pipeline = [
        {"$match": match_stage},
        {
            "$group": {
                "_id": {
                    "operational_date": "$operational_date",
                    "agency_id": "$agency_id",
                    "line_id": "$line_id",
                    "pattern_id": "$pattern_id",
                    "hour": { "$hour": { "$toDate": "$start_time_scheduled" } },
                },
                "ride_count": {"$sum": 1},
                "passengers_observed": {"$sum": "$passengers_observed"},
                "extension_sum": {"$sum": "$extension_scheduled"},
            }
        },
        {"$sort": {"_id.operational_date": 1, "_id.agency_id": 1, "_id.line_id": 1, "_id.hour": 1}},
    ]


    results = list(collection.aggregate(pipeline))
    df = pd.DataFrame(results)
    
    
# Flatten _id fields
    df["operational_date"] = df["_id"].apply(lambda x: x["operational_date"])
    df["agency_id"] = df["_id"].apply(lambda x: x["agency_id"])
    df["line_id"] = df["_id"].apply(lambda x: x.get("line_id"))
    df["pattern_id"] = df["_id"].apply(lambda x: x.get("pattern_id"))
    df["hour"] = df["_id"].apply(lambda x: x["hour"]) 
    df = df.drop(columns=["_id"])

    df.loc[(df["hour"] >= 4) & (df["hour"] < 6), "period_of_day"] = "4-6"
    df.loc[(df["hour"] >= 6) & (df["hour"] < 9), "period_of_day"] = "6-9"
    df.loc[(df["hour"] >= 9) & (df["hour"] < 13), "period_of_day"] = "9-13"
    df.loc[(df["hour"] >= 13) & (df["hour"] < 14), "period_of_day"] = "13-14"
    df.loc[(df["hour"] >= 14) & (df["hour"] < 17), "period_of_day"] = "14-17"
    df.loc[(df["hour"] >= 17) & (df["hour"] < 20), "period_of_day"] = "17-20"
    df.loc[(df["hour"] >= 20) & (df["hour"] < 24), "period_of_day"] = "20-0"
    df.loc[(df["hour"] >= 0) & (df["hour"] < 4), "period_of_day"] = "0-4"
    
    return df


def load_validations(start_date: str, end_date: str, line_ids: list[int] = None) -> pd.DataFrame:
    """
    Query MongoDB and return validations per trip per day, with zero-validation flag.

    Parameters
    ----------
    start_date : str (YYYYMMDD)
    end_date : str (YYYYMMDD)
    line_ids : list[int], optional

    Returns
    -------
    pd.DataFrame
    """
    client = MongoClient(config.MONGO_URI)
    db = client[config.DB_NAME]
    collection = db[config.COLLECTION_NAME]

    match_stage = {
        "operational_date": {"$gte": start_date, "$lte": end_date}
    }
    if line_ids:
        match_stage["line_id"] = {"$in": line_ids}

    pipeline = [
        {"$match": match_stage},
        {
            "$group": {
                "_id": {
                    "operational_date": "$operational_date",
                    "trip_id": "$trip_id",
                    "pattern_id": "$pattern_id",
                    "agency_id": "$agency_id",
                    "start_time_scheduled": "$start_time_scheduled",
                    "driver_ids": "$driver_ids",
                    "vehicle_ids": "$vehicle_ids",
                    "SIMPLE_THREE_VEHICLE_EVENTS": "$analysis.SIMPLE_THREE_VEHICLE_EVENTS.grade",
                },
                "validations": {"$sum": "$apex_validations_qty"},
            }
        },
        {
            "$project": {
                "pattern_id": "$_id.pattern_id",
                "agency_id": "$_id.agency_id",
                "trip_id": "$_id.trip_id",
                "start_time_scheduled": "$_id.start_time_scheduled",
                "operational_date": "$_id.operational_date",
                "driver_ids": "$_id.driver_ids",
                "vehicle_ids": "$_id.vehicle_ids",
                "SIMPLE_THREE_VEHICLE_EVENTS": "$_id.SIMPLE_THREE_VEHICLE_EVENTS",   
                "validations": 1,
                "has_zero": {"$eq": ["$validations", 0]},
            }
        },
        {"$sort": {"pattern_id": 1, "operational_date": 1}},
    ]

    results = list(collection.aggregate(pipeline))
    df_validations = pd.DataFrame(results)

    df_validations = df_validations.drop(columns=["_id"])

    return df_validations

def find_problematic_trips(df_validations: pd.DataFrame) -> pd.DataFrame:
    """
    Find trips with >=5 days of service, at least one day with >=30 validations,
    and report the days with 0 validations.
    """
    if df_validations is None or df_validations.empty:
        return pd.DataFrame()

    # Convert milliseconds to HH:MM
    df_validations["start_time"] = pd.to_datetime(
        df_validations["start_time_scheduled"], unit="ms"
    ).dt.strftime("%H:%M")
    
    # Days of service per (pattern_id, start_time)
    days_per_trip = df_validations.groupby(["pattern_id", "start_time"])["operational_date"].nunique()

    # Trips with >=5 days
    trips_5days = days_per_trip[days_per_trip >= 5].index

    # Trips with >=30 validations on at least one day
    trips_30plus = df_validations.groupby(["pattern_id", "start_time"])["validations"].max()
    trips_30plus = trips_30plus[trips_30plus >= 30].index

    # Intersection: trips meeting both conditions
    trips_selected = set(trips_5days).intersection(trips_30plus)

    # Filter rows where (pattern_id, start_time) is in trips_selected
    df_selected = df_validations[
        df_validations[["pattern_id", "start_time"]].apply(tuple, axis=1).isin(trips_selected)
    ]

    avg_validations = (
        df_selected.groupby(["pattern_id", "start_time"])["validations"].mean().reset_index(name="avg_validations")
    )

    # Keep only the days with 0 validations
    df_zero_days = df_selected[
        (df_selected["validations"] == 0) &
        (df_selected["SIMPLE_THREE_VEHICLE_EVENTS"] == "pass")
    ].copy()

    # Merge average into df_zero_days
    df_zero_days = df_zero_days.merge(avg_validations, on=["pattern_id", "start_time"], how="left")


    return df_zero_days


