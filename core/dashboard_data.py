"""Dashboard period selection; all aggregation and inference stay in core modules."""

from dataclasses import dataclass
from numbers import Integral

import pandas as pd

from core.data_cleaning import annual_mean_temperatures, annual_trend_ready
from core.trend_analysis import TrendResult, analyze_annual_trend
from core.i18n import t


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
        return DashboardPeriod(selected, empty, empty.copy(), None, t("notice.no_data"))
    annual = annual_mean_temperatures(selected)
    complete = annual_trend_ready(annual)
    if len(complete) < 3:
        return DashboardPeriod(selected, annual, complete, None,
                               t("notice.insufficient"))
    try:
        trend = analyze_annual_trend(complete)
    except ValueError:
        return DashboardPeriod(selected, annual, complete, None, t("notice.gaps"))
    return DashboardPeriod(selected, annual, complete, trend, None)


def annual_chart_data(period: DashboardPeriod) -> pd.DataFrame:
    """Keep missing-year gaps, but never plot partial means as annual averages."""
    table = period.annual.copy()
    for column in ("temperature_k", "temperature_c"):
        table[column] = table[column].where(table.is_complete)
    return table


def processed_csv(period: DashboardPeriod, frequency: str) -> bytes:
    """Export selected processed data, including incomplete annual summaries."""
    if frequency not in ("Annual", "Monthly"):
        raise ValueError("Frequency must be Annual or Monthly.")
    frame = period.annual if frequency == "Annual" else period.monthly
    return frame.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")


def interpret_trend(result: TrendResult, *, lang: str = "en") -> str:
    """Explain the same inference with complete localized sentence templates."""
    direction_key = "interpret.warming" if result.slope_per_year > 0 else "interpret.cooling" if result.slope_per_year < 0 else "interpret.zero"
    paragraphs = [t("interpret.trend", lang, start=result.years[0], end=result.years[-1],
                    slope=result.slope_per_decade, direction=t(direction_key, lang), years=len(result.years))]
    interval = result.hac.confidence_interval_per_decade
    if interval is not None:
        paragraphs.append(t("interpret.ci", lang, low=interval[0], high=interval[1]) +
                          t("interpret.significant" if result.hac.significant else "interpret.nonsignificant", lang))
    else:
        paragraphs.append(t("interpret.degenerate", lang))
    paragraphs.append(t("interpret.difference", lang, difference=result.first_to_last_difference))
    if result.diagnostics.autocorrelation_detected:
        paragraphs.append(t("interpret.dependence", lang))
    return "\n\n".join(paragraphs)
