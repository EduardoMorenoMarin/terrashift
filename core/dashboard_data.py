"""Dashboard period selection; all aggregation and inference stay in core modules."""

from dataclasses import dataclass
from numbers import Integral

import pandas as pd

from core.data_cleaning import annual_mean_temperatures, annual_trend_ready
from core.trend_analysis import TrendResult, analyze_annual_trend


@dataclass
class DashboardPeriod:
    monthly: pd.DataFrame
    annual: pd.DataFrame
    complete_annual: pd.DataFrame
    trend: TrendResult | None
    analysis_notice: str | None


def prepare_period(monthly: pd.DataFrame, start_year: int, end_year: int) -> DashboardPeriod:
    """Select full calendar years without changing inputs or dropping monthly values."""
    if any(isinstance(y, bool) or not isinstance(y, Integral) for y in (start_year, end_year)):
        raise ValueError("Start and end years must be integers.")
    if start_year > end_year:
        raise ValueError("Start year must be no later than end year.")
    selected = monthly.loc[monthly.date.dt.year.between(start_year, end_year)].copy()
    if selected.empty:
        empty = pd.DataFrame(columns=["year", "temperature_k", "temperature_c", "valid_months", "is_complete"])
        return DashboardPeriod(selected, empty, empty.copy(), None, "No temperature data is available for this period.")
    annual = annual_mean_temperatures(selected)
    complete = annual_trend_ready(annual)
    if len(complete) < 3:
        return DashboardPeriod(selected, annual, complete, None,
                               "Choose at least three complete, consecutive years to estimate a trend. Temperature data is still shown below.")
    try:
        trend = analyze_annual_trend(complete)
    except ValueError:
        return DashboardPeriod(selected, annual, complete, None, "A trend could not be estimated for this period. Choose a different range of consecutive years with complete data.")
    return DashboardPeriod(selected, annual, complete, trend, None)


def processed_csv(period: DashboardPeriod, frequency: str) -> bytes:
    """Export selected processed data, including incomplete annual summaries."""
    if frequency not in ("Annual", "Monthly"):
        raise ValueError("Frequency must be Annual or Monthly.")
    frame = period.annual if frequency == "Annual" else period.monthly
    return frame.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")


def interpret_trend(result: TrendResult) -> str:
    """Explain a computed annual trend without changing its inference."""
    direction = "warming" if result.slope_per_year > 0 else "cooling" if result.slope_per_year < 0 else "no estimated linear change"
    paragraphs = [
        f"From {result.years[0]} to {result.years[-1]}, the estimated trend is "
        f"**{result.slope_per_decade:+.3f} °C per decade**, indicating {direction}. "
        f"The estimate uses {len(result.years)} complete years."
    ]
    interval = result.hac.confidence_interval_per_decade
    if interval is not None:
        uncertainty = (f"The **95% confidence interval is {interval[0]:+.3f} to {interval[1]:+.3f} °C per decade**. ")
        if result.hac.significant:
            uncertainty += "This provides statistical evidence of a trend over the selected period, under the analysis assumptions."
        else:
            uncertainty += "The interval includes zero, so the direction of change remains uncertain. This does not mean temperatures stayed the same."
        paragraphs.append(uncertainty)
    else:
        paragraphs.append("Statistical uncertainty cannot be assessed because the annual values follow an almost exact line. Confidence intervals and p-values are unavailable for this fit.")
    paragraphs.append(
        f"The last annual average is **{result.first_to_last_difference:+.3f} °C** relative to the first. "
        "This first-to-last change compares two years; the trend summarizes all years in the period."
    )
    if result.diagnostics.autocorrelation_detected:
        paragraphs.append("Year-to-year patterns remain after fitting the trend. The confidence interval uses HAC adjustment to account for short-range dependence, though uncertainty is harder to estimate in a short record.")
    return "\n\n".join(paragraphs)
