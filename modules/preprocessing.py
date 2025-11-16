import pandas as pd
from zoneinfo import ZoneInfo


def prepare(df: pd.DataFrame, daytype_file: str) -> pd.DataFrame:
    """
    Preprocess rides dataframe:
    - convert dates
    - merge with daytypes
    - add month, extensions_k, and period of day
    """
    # Convert YYYYMMDD → datetime
    df["operational_date"] = pd.to_datetime(df["operational_date"], format="%Y%m%d")

    # Load daytypes
    daytypes = pd.read_csv(daytype_file)  # must have: date, day_type
    daytypes["date"] = pd.to_datetime(daytypes["date"], format="%Y%m%d")
    daytypes.rename(columns={"date": "operational_date"}, inplace=True)

    # Merge
    df = df.merge(daytypes, on="operational_date", how="left")

    # Extra cols
    df["month"] = df["operational_date"].dt.to_period("M").dt.strftime("%m/%Y")
    df["extensions_k"] = df["extension_sum"] / 1000

    return df

def prepare_to_zeros(df: pd.DataFrame, daytype_file: str) -> pd.DataFrame:
    """
    Preprocess rides dataframe:
    - convert dates
    - merge with daytypes
    - add month, extensions_k, and period of day
    """
    # Convert YYYYMMDD → datetime
    df["operational_date"] = pd.to_datetime(df["operational_date"], format="%Y%m%d")

    # Load daytypes
    daytypes = pd.read_csv(daytype_file)  # must have: date, day_type
    daytypes["date"] = pd.to_datetime(daytypes["date"], format="%Y%m%d")
    daytypes.rename(columns={"date": "operational_date"}, inplace=True)

    # Merge
    df = df.merge(daytypes, on="operational_date", how="left")

    # Extra cols
    df["month"] = df["operational_date"].dt.to_period("M").dt.strftime("%m/%Y")

    return df
