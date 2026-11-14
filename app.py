"""TerraShift AI: run with `python -m streamlit run app.py`."""

import logging
from pathlib import Path

import streamlit as st

from core.region_data import load_country, read_country_mapping
from core.dashboard_data import prepare_period, processed_csv, interpret_trend
from core.dashboard_copy import display_temperature_data
from core.dashboard_charts import temperature_figure, comparison_temperature_figure, warming_rate_figure
from core.country_comparison import (available_countries, country_colors, prepare_comparison,
                                     comparison_table, interpret_comparison)
from core.map_data import load_map_data
from core.map_charts import country_trend_figure

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)

st.set_page_config(page_title="TerraShift AI | South American temperature trends", page_icon="🌎", layout="wide")
st.markdown("""<style>
.block-container {max-width: 1240px; padding-top: 2rem;}
[data-testid="stMetric"] {background: white; border: 1px solid #dce6ec;
border-radius: 12px; padding: 1rem; height: 100%;}
[data-testid="stMetricValue"] {font-size: clamp(1.2rem, 2vw, 1.8rem);}
</style>""", unsafe_allow_html=True)


def render_map(country, start, end, registry_path):
    st.subheader(f"South America · temperature trends · {start}–{end}")
    st.caption("Colors represent trends in country-level average temperatures, not within-country spatial variation. Each country has one estimate; colors do not indicate statistical significance.")
    try:
        table, boundaries = load_map_data(start, end, mapping_path=registry_path,
                                          raw_directory=ROOT / "data/raw")
    except (OSError, ValueError, KeyError):
        LOGGER.exception("Unable to prepare the South America map")
        st.info("The map is temporarily unavailable. Country temperature details remain available below.")
        return
    selected_iso3 = table.loc[table.Country.eq(country), "ISO-3"].iloc[0]
    st.plotly_chart(country_trend_figure(table, boundaries, selected_iso3),
                    width="stretch", key="country_trend_map", on_select="ignore",
                    config={"displaylogo": False, "scrollZoom": False})
    st.caption(f"Hover over a country for its trend and period; use the Country to explore selector in the sidebar to see details below. The dark outline marks {country}. Zoom with the map controls and drag to pan.")
    st.caption("Boundaries: [Natural Earth](https://www.naturalearthdata.com/), 1:110m Admin 0 countries, v5.1.2 · [Public domain](https://www.naturalearthdata.com/about/terms-of-use/). Display boundaries may differ from the Giovanni selections used to calculate country averages.")
    missing = table["Trend (°C/decade)"].isna()
    if missing.any():
        st.info("Gray countries have unavailable trends: " + ", ".join(table.loc[missing, "Country"]) + ". At least three complete, consecutive years are needed; source data may also be unavailable.")
    if end - start + 1 < 10:
        st.warning("Short periods can give sensitive trend estimates. Try a longer period for a broader view.")
    with st.expander("Map estimates & availability"):
        st.dataframe(table.drop(columns=["ISO-3"]), hide_index=True,
                     column_config={"Trend (°C/decade)": st.column_config.NumberColumn(format="%.4f")})


def render_explore(dataset, country, start, end, frequency, show_trend, color):
    period = prepare_period(dataset.monthly, start, end)
    result = period.trend
    st.subheader(f"{country} · {start}–{end}")
    st.caption(f"Air temperature at 2 meters · {len(period.complete_annual)} complete years · {len(period.monthly)} monthly values")
    if dataset.missing_months:
        st.warning(f"{len(dataset.missing_months)} months are missing from the source record. Only available data is shown.")
    if period.analysis_notice:
        st.info(period.analysis_notice)
    if result is not None:
        a, b, c = st.columns(3)
        a.metric("Temperature trend", f"{result.slope_per_decade:+.3f} °C/decade",
                 help="Average rate of change estimated from all complete years in this period.")
        b.metric("Trend p-value", "Unavailable" if result.hac.p_value is None else f"{result.hac.p_value:.4g}",
                 help="Tests a zero trend using HAC-adjusted uncertainty. Values below 0.05 indicate statistical evidence of a trend under the analysis assumptions.")
        interval = result.hac.confidence_interval_per_decade
        c.metric("95% confidence interval · °C/decade", "Unavailable" if interval is None else f"{interval[0]:+.3f} to {interval[1]:+.3f}",
                 help="Uncertainty in the estimated rate of change, adjusted for year-to-year dependence.")
        a, b, c = st.columns(3)
        a.metric("R² · fit strength", "Unavailable" if result.r_squared is None else f"{result.r_squared:.3f}",
                 help="The share of variation in annual temperatures described by the linear trend.")
        b.metric("First-to-last change", f"{result.first_to_last_difference:+.3f} °C",
                 help="Difference between the last and first annual averages. The trend estimate uses all years.")
        c.metric("Years analyzed", str(len(result.years)))
    with st.container(border=True):
        st.subheader(f"{frequency} average temperature")
        st.plotly_chart(temperature_figure(period, frequency, show_trend, color=color), width="stretch", config={"displaylogo": False})
        if frequency == "Monthly":
            st.caption("Monthly values show the seasonal cycle. Trend estimates use annual averages.")
        else:
            st.caption("Points show annual averages. The dashed line, when shown, summarizes the linear trend.")
        if len(period.annual) != len(period.complete_annual):
            st.caption("Years with missing months appear in the data table but are excluded from the trend estimate.")
    st.subheader("What do these results mean?")
    if result is not None:
        st.markdown(interpret_trend(result))
        if len(result.years) < 10:
            st.warning("Short periods can give sensitive trend estimates. Try a longer period for a broader view.")
    else:
        st.write("Temperature data is shown for the selected period. Choose a longer range to estimate a trend.")
    with st.expander("Data & diagnostics"):
        if result is not None:
            st.markdown(f"**Uncertainty estimates:** {len(result.years)} years analyzed; HAC adjustment uses {result.hac_lags} annual lags.")
            st.dataframe([
                {"Method": method,
                 "95% confidence interval (°C/decade)": (
                     f"{inference.confidence_interval_per_decade[0]:+.6f} to {inference.confidence_interval_per_decade[1]:+.6f}"
                     if inference.confidence_interval_per_decade is not None else "Unavailable"),
                 "Trend p-value": inference.p_value}
                for method, inference in (("Ordinary least squares (OLS)", result.ols), ("Newey–West (HAC)", result.hac))
            ], hide_index=True)
            d = result.diagnostics
            st.markdown("**Residual diagnostics** · Checks on the differences between annual temperatures and the fitted trend.")
            st.dataframe([
                {"Diagnostic": "Lag-1 residual correlation", "Value": d.lag1_correlation},
                {"Diagnostic": "Durbin–Watson statistic", "Value": d.durbin_watson},
                {"Diagnostic": "Ljung–Box p-value (exploratory)", "Value": d.ljung_box_p_value},
                {"Diagnostic": "Residual root mean square error (°C)", "Value": d.rmse},
            ], hide_index=True)
            if d.autocorrelation_detected:
                st.info("The residual check suggests year-to-year dependence. Adjusted uncertainty is shown alongside the conventional OLS estimate above.")
            elif d.autocorrelation_detected is False:
                st.caption("The residual check did not flag year-to-year dependence; this check alone cannot establish independence.")
            else:
                st.caption("Residual dependence cannot be assessed for this fit.")
            if d.potential_outlier_years or d.influential_years:
                unusual = ", ".join(str(year) for year in d.potential_outlier_years) or "None flagged"
                influential = ", ".join(str(year) for year in d.influential_years) or "None flagged"
                st.caption(f"Years with unusually large residuals: {unusual}. Years with greater influence on the fit: {influential}. All years are retained.")
        st.markdown("**Temperature data for this selection**")
        st.dataframe(display_temperature_data(period, frequency), hide_index=True)
        st.download_button(
            "Download temperature data (CSV)", processed_csv(period, frequency),
            file_name=f"terrashift_{country.lower()}_{frequency.lower()}_{start}_{end}.csv", mime="text/csv",
            on_click="ignore", key="download_data",
        )
        st.caption("The download includes the selected years and frequency. Annual files also identify years with missing months.")


def render_methodology(registry_path):
    st.subheader("About the data")
    st.markdown("""
TerraShift AI is a NASA Space Apps Challenge project using **NASA MERRA-2**
data distributed through Giovanni. It explores average air temperature
2 meters above the surface across 12 South American countries.

MERRA-2 is a **reanalysis**: it combines weather observations with a physical
model to estimate past conditions. These country averages describe regional
patterns rather than individual thermometer readings or local extremes.
""")
    st.subheader("From monthly temperatures to trends")
    st.markdown("""
Temperatures are converted from Kelvin to Celsius. Annual averages give equal
weight to each month; a year needs all 12 monthly values to enter the trend
analysis. Available records are retained without interpolation or outlier removal.

A straight-line regression estimates the rate of change in **°C per decade**.
The 95% confidence interval describes uncertainty in that rate. The Newey–West
method, also called HAC, adjusts uncertainty for year-to-year dependence and
changes in variability. It is an approximation, especially for short records.
""")
    st.subheader("Reading the results")
    st.markdown("""
A trend p-value below **0.05** indicates statistical evidence of a change under
the analysis assumptions. An interval that includes zero leaves the direction
uncertain; it does not mean temperatures stayed the same. A small p-value says
little about the practical importance of the change or its causes.

Temperature levels and warming rates answer different questions. Countries
have different climates, elevations, and geography, so a warmer country need
not be warming more quickly. Trends are estimated separately for each country.
Differences between countries should be interpreted cautiously: individual
trend tests do not establish that their rates differ statistically.

Country averages can hide local and seasonal changes. The selected period,
natural variability, and the length of the record all affect the estimates.
These results describe temperature changes, rather than what caused them.
""")
    st.subheader("Country boundaries and data sources")
    st.write("Country-level temperature series were obtained through NASA Giovanni using individual country boundary selections. Geographic selections were made during data extraction, and original Giovanni boundary references are retained for traceability.")
    registry = read_country_mapping(registry_path)
    st.dataframe([{"Country": name, "Data source": "NASA MERRA-2 via Giovanni"}
                  for name in registry], hide_index=True)
    with st.expander("Technical details"):
        st.markdown("""
**Collection:** M2TMNXSLV v5.12.4. **Variable:** T2M (2-meter air temperature).
Monthly area-averaged data; source grid: 0.5° × 0.625°. **Conversion:** °C = K − 273.15.
Annual means are equally weighted across months, rather than weighted by month length.

**Inference:** ordinary least squares with an intercept; HAC uses Bartlett weights,
correction n/(n−2), and lag rule floor(4 × (n/100)^(2/9)), capped at n−1.
OLS and HAC share the same slope. Both use two-sided Student-t intervals with
n−2 degrees of freedom; HAC's reference distribution is approximate.
Conventional OLS uncertainty assumes independent errors with constant variance;
year-to-year dependence can make it unreliable.

**Diagnostics:** the exploratory Ljung–Box screen uses up to three lags.
Potential outliers have absolute internally standardized residuals above 2;
Cook's distance above 4/n flags possible influence. Flags prompt review, not removal.

**Country comparisons:** each p-value tests that country's slope against zero.
P-values are not adjusted for multiple testing. Comparing individual confidence
intervals does not replace a direct test of differences between country trends.
Bars alone do not establish a definitive warming-rate ranking.

**Boundary traceability:** country selections and filename labels were recorded
by the project during extraction. Original Giovanni shape references are listed
below. The export does not include polygon coordinates or detailed spatial
averaging information.
""")
        st.dataframe([{"Country": name, "Giovanni boundary reference": entry["shape_identifier"]}
                      for name, entry in registry.items()], hide_index=True)
    st.markdown("[NASA MERRA-2 overview](https://gmao.gsfc.nasa.gov/gmao-products/merra-2/) · "
                "[Collection documentation](https://doi.org/10.5067/AP1B0BA5PD2K) · "
                "[Variable and unit reference](https://gmao.gsfc.nasa.gov/gmaoftp/mikeb/Harvey/MERRA2.README.pdf) · "
                "[NASA Giovanni](https://giovanni.gsfc.nasa.gov/giovanni/)")


def render_compare(selected, start, end, frequency, colors):
    st.subheader(f"Compare countries · {start}–{end}")
    if len(selected) < 2:
        st.info("Select 2–5 countries in the sidebar to compare temperatures and rates of change.")
        return
    try:
        periods = prepare_comparison(selected, start, end,
                                     mapping_path=ROOT / "metadata/country_mapping.json",
                                     raw_directory=ROOT / "data/raw")
    except (ValueError, OSError):
        LOGGER.exception("Unable to prepare the selected country comparison")
        st.error("The comparison could not be loaded. Check your country selection and try again.")
        return
    st.subheader(f"{frequency} average temperatures")
    st.plotly_chart(comparison_temperature_figure(periods, frequency, colors),
                   width="stretch", config={"displaylogo": False}, key="comparison_temperatures")
    st.caption("A warmer country is not necessarily warming faster. Temperature levels reflect geography, elevation, and climate.")
    if frequency == "Monthly":
        st.caption("Monthly values show the seasonal cycle; trend estimates use annual averages.")
    for country, period in periods.items():
        if period.analysis_notice:
            st.info(f"{country}: {period.analysis_notice}")
    st.subheader("Temperature trends")
    if any(period.trend is not None for period in periods.values()):
        st.plotly_chart(warming_rate_figure(periods, colors), width="stretch",
                       config={"displaylogo": False}, key="comparison_rates")
        st.caption("Whiskers show adjusted 95% confidence intervals. * marks an individually significant trend (p < 0.05). Trends that cannot be estimated remain in the table below.")
    else:
        st.info("Choose at least three complete, consecutive years per country to compare trends. Temperature data remains visible above.")
    st.subheader("Trend estimates")
    st.dataframe(comparison_table(periods), hide_index=True, column_config={
        "Trend (°C/decade)": st.column_config.NumberColumn(format="%.4f"),
        "Trend p-value": st.column_config.NumberColumn(format="%.6g"),
        "R²": st.column_config.NumberColumn("R² · fit strength", format="%.4f",
                                            help="Share of annual temperature variation described by the linear trend."),
    })
    st.subheader("What does the comparison show?")
    st.markdown(interpret_comparison(periods))
    if end - start + 1 < 10:
        st.warning("Short periods can give sensitive trend estimates. Try a longer period for a broader view.")


def main():
    st.caption("NASA SPACE APPS CHALLENGE PROJECT")
    st.title("TerraShift AI")
    st.header("Explore South America's changing temperatures")
    st.write("Track air temperature across 12 countries from 2000 to 2025. Compare temperature histories and estimated rates of change using NASA MERRA-2 data.")
    registry_path = ROOT / "metadata/country_mapping.json"
    try:
        countries = available_countries(registry_path)
        if not countries:
            raise ValueError("No resolved country entries are available.")
        colors = country_colors(countries)
    except (ValueError, OSError):
        LOGGER.exception("Unable to read the country registry")
        st.error("Country data is temporarily unavailable. Please try again later.")
        st.stop()
    with st.sidebar:
        st.title("🌎 TerraShift AI")
        st.caption("SOUTH AMERICA · TEMPERATURE EXPLORER")
        country = st.selectbox("Country to explore", countries,
                               index=countries.index("Peru") if "Peru" in countries else 0, key="country")
        selected = st.multiselect("Countries to compare (2–5)", countries, default=[],
                                 max_selections=5, key="compare_countries")
    try:
        dataset = load_country(country, mapping_path=registry_path, raw_directory=ROOT / "data/raw")
    except (ValueError, OSError, KeyError):
        LOGGER.exception("Unable to load temperature data for %s", country)
        st.error(f"Temperature data for {country} is temporarily unavailable.")
        st.info("Choose another country or try again later.")
        st.stop()
    years = sorted(int(year) for year in dataset.monthly.date.dt.year.unique())
    with st.sidebar:
        st.subheader("Time period")
        start = st.selectbox("Start year", years, index=0, key="start_year")
        end = st.selectbox("End year", years, index=len(years) - 1, key="end_year")
        frequency = st.radio("Temperature view", ["Annual", "Monthly"], key="frequency")
        show_trend = st.toggle("Show trend line in Explore", value=True,
                               disabled=frequency == "Monthly", key="show_trend")
        st.caption("Time period applies to the map, Explore and Compare. Temperature view applies to the temperature charts. Trends use annual averages.")
        st.divider()
        st.markdown("**NASA MERRA-2**  \n2-meter air temperature  \nMonthly data · 2000–2025")
    st.divider()
    if start > end:
        st.warning("Start year must be no later than end year. Adjust the time period to continue.")
        st.stop()
    explore, compare, methodology = st.tabs(["Explore", "Compare", "Methodology"])
    with explore:
        render_map(country, start, end, registry_path)
        render_explore(dataset, country, start, end, frequency, show_trend, colors[country])
    with compare:
        render_compare(selected, start, end, frequency, colors)
    with methodology:
        render_methodology(registry_path)
    st.divider()
    st.caption("TerraShift AI · NASA Space Apps Challenge project · Data: NASA MERRA-2")


if __name__ == "__main__":
    main()
