"""Explicit unit conversion and calendar-year summaries; no imputation."""

import pandas as pd


def kelvin_to_celsius(values):
    """Convert a scalar or numeric array/Series, preserving missing values."""
    return values - 273.15


def clean_monthly(observations: pd.DataFrame) -> pd.DataFrame:
    """Return an independent monthly table from validated loader output."""
    monthly = observations[["date", "temperature_k"]].copy()
    monthly["temperature_c"] = kelvin_to_celsius(monthly["temperature_k"])
    return monthly


def annual_mean_temperatures(monthly: pd.DataFrame) -> pd.DataFrame:
    """Arithmetic monthly means, valid counts, and completeness per year.

    Partial means remain available but must not enter annual trend inputs.
    Years entirely absent between the first and last record are included.
    """
    if monthly.empty:
        raise ValueError("Cannot aggregate an empty monthly table.")
    dates = monthly["date"]
    if dates.isna().any() or dates.dt.to_period("M").duplicated().any():
        raise ValueError("Annual aggregation requires one valid timestamp per month.")
    annual = monthly.groupby(dates.dt.year).agg(
        temperature_k=("temperature_k", "mean"),
        temperature_c=("temperature_c", "mean"),
        valid_months=("temperature_k", "count"),
    ).reindex(range(dates.dt.year.min(), dates.dt.year.max() + 1))
    annual.index.name = "year"
    annual["valid_months"] = annual["valid_months"].fillna(0).astype(int)
    annual["is_complete"] = annual["valid_months"].eq(12)
    return annual.reset_index()


def annual_trend_ready(annual: pd.DataFrame) -> pd.DataFrame:
    """Select complete years only, without fitting a trend."""
    return annual.loc[annual["is_complete"]].reset_index(drop=True).copy()
