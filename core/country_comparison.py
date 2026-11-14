"""Registry-based comparison preparation; statistics are delegated to existing core."""

from pathlib import Path

import pandas as pd

from core.dashboard_data import DashboardPeriod, prepare_period
from core.region_data import MAPPING_PATH, RAW_DIRECTORY, load_country, read_country_mapping

# One distinct color per registered country, assigned alphabetically so selection
# order does not change a country's color. Shared by Explore and Compare.
PALETTE = ("#007F86", "#C05B26", "#4667B4", "#9C4893", "#488028", "#A07800",
           "#CF4D68", "#6E5C46", "#576D7D", "#7A52CC", "#007DB7", "#B54322")


def available_countries(mapping_path: str | Path = MAPPING_PATH) -> list[str]:
    return sorted(country for country, entry in read_country_mapping(mapping_path).items()
                  if entry["status"] != "pending_confirmation")


def country_colors(countries: list[str]) -> dict[str, str]:
    """Pass the full registry's available countries for stable cross-view colors."""
    names = sorted(set(countries))
    if len(names) > len(PALETTE):
        raise ValueError("The color palette supports at most 12 countries.")
    return dict(zip(names, PALETTE))


def prepare_comparison(countries: list[str], start_year: int, end_year: int, *,
                       mapping_path: str | Path = MAPPING_PATH,
                       raw_directory: str | Path = RAW_DIRECTORY) -> dict[str, DashboardPeriod]:
    """Load 2–5 distinct confirmed countries and prepare the same selected period."""
    if not 2 <= len(countries) <= 5:
        raise ValueError("Select 2–5 countries for comparison.")
    if not all(isinstance(country, str) for country in countries) or len(set(countries)) != len(countries):
        raise ValueError("Select distinct country names.")
    available = available_countries(mapping_path)
    invalid = [country for country in countries if country not in available]
    if invalid:
        raise ValueError(f"Unknown or unresolved country selection: {', '.join(invalid)}.")
    periods = {}
    for country in countries:
        dataset = load_country(country, mapping_path=mapping_path, raw_directory=raw_directory)
        periods[country] = prepare_period(dataset.monthly, start_year, end_year)
    return periods


def comparison_table(periods: dict[str, DashboardPeriod]) -> pd.DataFrame:
    """Individual trend inference only; no test of differences between slopes."""
    rows = []
    for country, period in periods.items():
        result = period.trend
        years = result.years if result else tuple(period.annual.year)
        interval = result.hac.confidence_interval_per_decade if result else None
        significant = result.hac.significant if result else None
        rows.append({
            "Country": country,
            "Analysis period": f"{years[0]}–{years[-1]}" if years else "Unavailable",
            "Years analyzed": len(period.complete_annual),
            "Trend (°C/decade)": result.slope_per_decade if result else None,
            "95% confidence interval (°C/decade)": f"{interval[0]:+.3f} to {interval[1]:+.3f}" if interval else "Unavailable",
            "Trend p-value": result.hac.p_value if result else None,
            "R²": result.r_squared if result else None,
            "Trend significance": "Unavailable" if significant is None else "Statistically significant" if significant else "Not statistically significant",
        })
    return pd.DataFrame(rows)


def interpret_comparison(periods: dict[str, DashboardPeriod]) -> str:
    """Summarize individual country fits in short, public-facing paragraphs."""
    results = {country: period.trend for country, period in periods.items() if period.trend is not None}
    positive = [country for country, result in results.items() if result.slope_per_year > 0]
    negative = [country for country, result in results.items() if result.slope_per_year < 0]
    zero = [country for country, result in results.items() if result.slope_per_year == 0]
    significant = [country for country, result in results.items() if result.hac.significant is True]
    nonsignificant = [country for country, result in results.items() if result.hac.significant is False]
    unavailable = [country for country, period in periods.items()
                   if period.trend is None or period.trend.hac.significant is None]
    direction = []
    if positive:
        direction.append(f"Estimated warming: **{', '.join(positive)}**.")
    if negative:
        direction.append(f"Estimated cooling: **{', '.join(negative)}**.")
    if zero:
        direction.append(f"No estimated linear change: **{', '.join(zero)}**.")
    paragraphs = [" ".join(direction)] if direction else []
    if significant:
        paragraphs.append(f"Statistical evidence of an individual trend: **{', '.join(significant)}**. "
                          "Each adjusted 95% confidence interval excludes zero, under the analysis assumptions.")
    if nonsignificant:
        paragraphs.append(f"The direction of change remains uncertain for **{', '.join(nonsignificant)}**: "
                          "the adjusted intervals include zero. This does not mean temperatures stayed the same.")
    if unavailable:
        paragraphs.append(f"Trend uncertainty cannot be assessed for **{', '.join(unavailable)}**. "
                          "This can occur with too few complete years or an almost exact linear fit.")
    paragraphs.append("Trends are estimated separately for each country. Differences between countries should be interpreted cautiously; "
                      "the table does not test whether their rates of change differ statistically. "
                      "The results describe changes over the selected period, rather than what caused them.")
    return "\n\n".join(paragraphs)
