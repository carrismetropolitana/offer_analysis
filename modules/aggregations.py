import pandas as pd


def aggregate(df: pd.DataFrame, group_fields: list[str], metrics: dict) -> pd.DataFrame:
    """
    Generic aggregation function.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    group_fields : list[str]
        Columns to group by.
    metrics : dict
        Dictionary of columns and aggregation functions.
        Example: {"ride_count": "sum", "extensions_k": "sum"}

    Returns
    -------
    pd.DataFrame
        Aggregated dataframe.
    """
    missing_metrics = [col for col in metrics.keys() if col not in df.columns]
    if missing_metrics:
        raise ValueError(f"Missing columns in dataframe: {missing_metrics}")

    missing_groups = [col for col in group_fields if col not in df.columns]
    if missing_groups:
        raise ValueError(f"Missing group fields in dataframe: {missing_groups}")

    return df.groupby(group_fields, as_index=False).agg(metrics)


# -------------------------
# Aggregation functions
# -------------------------

def agg_monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly rides and extensions per agency."""
    return aggregate(df, ["month", "agency_id"], {
        "ride_count": "sum",
        "extensions_k": "sum"
    })


def agg_daytype_monthly_avg(df: pd.DataFrame) -> pd.DataFrame:
    """Average rides per day_type per month and agency."""
    grouped = df.groupby(["month",  "day_type","agency_id"], as_index=False).agg(
        n_days=("operational_date", "nunique"),
        ride_count=("ride_count", "sum")        
    )
    grouped["avg_rides_per_day"] = grouped["ride_count"] / grouped["n_days"]
    return grouped



def agg_daytype_total(df: pd.DataFrame) -> pd.DataFrame:
    """Average rides per day_type per agency (whole period)."""
    grouped = df.groupby(["agency_id", "day_type"], as_index=False).agg(
        total_rides=("ride_count", "sum"),
        n_days=("operational_date", "nunique")
    )
    grouped["avg_rides_per_day"] = grouped["total_rides"] / grouped["n_days"]
    return grouped


def agg_daytype_date(df: pd.DataFrame) -> pd.DataFrame:
    """Daily breakdown by day_type."""
    return aggregate(df, ["agency_id", "line_id", "pattern_id","operational_date", "day_type", "period"], {
        "ride_count": "sum",
        "passengers_observed": "sum"
    }).rename(columns={"ride_count": "rides"})


def agg_lineid_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rides and extensions per line_id,
    broken down by month, day_type, period (analysis period), 
    period_of_day, and agency.
    """
    return aggregate(
        df,
        ["agency_id", "line_id","month", "day_type", "period", "period_of_day"],
        {
            "ride_count": "sum",
            "extension_sum": "sum"
        }
    ).rename(columns={
        "ride_count": "total_rides",
        "extension_sum": "total_extensions"
    })


def agg_lineid_daytype_period(df: pd.DataFrame) -> pd.DataFrame:
    """Rides per line_id, day_type, and period (whole period)."""
    return aggregate(df, ["line_id", "day_type", "period"], {
        "ride_count": "sum"
    }).rename(columns={"ride_count": "rides"})

def create_suspect_trips(df: pd.DataFrame) -> pd.DataFrame:
    required_cols = [
        "operational_date", "day_type", "period", "month", "agency_id",
 "pattern_id", "trip_id", "start_time", "validations", "avg_validations",
        "driver_ids", "vehicle_ids"    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in dataframe: {missing}")
    return df[required_cols].copy()