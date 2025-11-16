import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd


def plot_timeseries(df: pd.DataFrame, value_col: str, ylabel: str,
                    title: str, output_path: str) -> plt.Figure:
    """
    Generic timeseries plot for agencies.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: ["month", "agency_id", value_col].
    value_col : str
        Column to plot on Y axis.
    ylabel : str
        Label for Y axis.
    title : str
        Title of the plot.
    output_path : str
        Where to save the PNG file.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    for agency in df["agency_id"].unique():
        agency_data = df[df["agency_id"] == agency]
        ax.plot(agency_data["month"], agency_data[value_col], marker="o", label=f"Agency {agency}")

        # Annotate last value
        if not agency_data.empty:
            last_x, last_y = agency_data["month"].iloc[-1], agency_data[value_col].iloc[-1]
            ax.text(last_x, last_y, f"{last_y:,}", fontsize=9, ha="left", va="bottom")

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Month")
    ax.grid(True)
    ax.legend(title="Agency ID", bbox_to_anchor=(1.05, 1), loc="upper left")

    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    return fig


def plot_monthly_rides(df_monthly: pd.DataFrame, output_path: str) -> plt.Figure:
    """Wrapper: Monthly rides by agency."""
    return plot_timeseries(df_monthly, "ride_count", "Ride Count",
                           "Monthly Ride Count by Agency", output_path)


def plot_monthly_extensions(df_monthly: pd.DataFrame, output_path: str) -> plt.Figure:
    """Wrapper: Monthly extensions by agency."""
    return plot_timeseries(df_monthly, "extensions_k", "Extensions (k)",
                           "Monthly Extensions by Agency", output_path)


def plot_daytype_bar(df_daytype_month_avg: pd.DataFrame, output_path: str) -> plt.Figure:
    """
    Bar chart: avg rides per day_type monthly (all agencies).
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    sns.barplot(
        data=df_daytype_month_avg,
        x="month", y="avg_rides_per_day",
        hue="day_type", ax=ax
    )
    ax.set_title("Average Rides per Day Type (Monthly, All Agencies)")
    ax.set_ylabel("Avg rides per day")
    ax.set_xlabel("Month")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(title="Day Type")
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    return fig
