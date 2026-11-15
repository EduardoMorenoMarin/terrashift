"""TerraShift: run with `python -m streamlit run app.py`."""

import logging
from pathlib import Path
from functools import partial

import streamlit as st

from core.region_data import load_country, read_country_mapping
from core.dashboard_data import prepare_period, processed_csv, interpret_trend
from core.dashboard_copy import display_temperature_data
from core.dashboard_charts import temperature_figure, comparison_temperature_figure, warming_rate_figure
from core.country_comparison import (available_countries, country_colors, prepare_comparison,
                                     comparison_table, interpret_comparison)
from core.map_data import load_map_data
from core.map_charts import country_trend_figure
from core.i18n import t, country_name, plural, LANGUAGES, catalogs
from core.dashboard_copy import localize_table, localize_notice, chart_config, coverage_labels, source_request_notice
from core.dashboard_state import begin_presentation, analysis_value, localized_tabs

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)

# Refresh public copy on reruns even when the server retains imported modules.
catalogs.cache_clear()

st.markdown("""<style>
.block-container {max-width: 1240px; padding-top: 2rem;}
[data-testid="stMetric"] {background: white; border: 1px solid #dce6ec;
border-radius: 12px; padding: 1rem; height: 100%;}
[data-testid="stMetricValue"] {font-size: clamp(1.2rem, 2vw, 1.8rem);}
</style>""", unsafe_allow_html=True)


def render_map(country, start, end, registry_path, lang="en"):
    tr = partial(t, lang=lang)
    st.subheader(tr("map.heading", start=start, end=end))
    st.caption(tr('map.scope'))
    try:
        table, boundaries = analysis_value("map", (start, end), lambda: load_map_data(
            start, end, mapping_path=registry_path, raw_directory=ROOT / "data/raw"))
    except (OSError, ValueError, KeyError):
        LOGGER.exception("Unable to prepare the South America map")
        st.info(tr('map.error'))
        return
    selected_iso3 = table.loc[table.Country.eq(country), "ISO-3"].iloc[0]
    st.plotly_chart(country_trend_figure(table, boundaries, selected_iso3, lang=lang),
                    width="stretch", key="country_trend_map", on_select="ignore",
                    config=chart_config(lang, scrollZoom=False))
    st.caption(tr("map.instructions", country=country_name(country, lang)))
    st.caption(tr('map.attribution'))
    missing = table["Trend (°C/decade)"].isna()
    if missing.any():
        st.info(tr("map.missing", countries=", ".join(country_name(name, lang) for name in table.loc[missing, "Country"])))
    if end - start + 1 < 10:
        st.warning(tr('common.short_period'))
    with st.expander(tr('map.estimates')):
        st.dataframe(localize_table(table.drop(columns=["ISO-3"]), lang), hide_index=True,
                     column_config={tr('column.trend'): st.column_config.NumberColumn(format="%.4f")})


def render_explore(dataset, country, start, end, frequency, show_trend, color, lang="en"):
    tr = partial(t, lang=lang)
    period = analysis_value("explore", (country, start, end), lambda: prepare_period(dataset.monthly, start, end))
    result = period.trend
    st.subheader(tr("common.country_period", country=country_name(country, lang), start=start, end=end))
    st.caption(tr("explore.coverage", years=plural("count.complete_year", len(period.complete_annual), lang),
                           months=plural("count.monthly_value", len(period.monthly), lang)))
    if dataset.missing_months:
        st.warning(plural("count.missing_month", len(dataset.missing_months), lang))
    if period.analysis_notice:
        st.info(localize_notice(period.analysis_notice, lang))
    if result is not None:
        st.caption(tr('coverage.trend_period', start=start, end=end,
                      fit_start=result.years[0], fit_end=result.years[-1]))
        a, b, c = st.columns(3)
        a.metric(tr('metric.trend'), f"{result.slope_per_decade:+.3f} {tr('unit.trend')}",
                 help=tr('metric.trend_help'))
        b.metric(tr('metric.p'), tr('common.unavailable') if result.hac.p_value is None else f"{result.hac.p_value:.4g}",
                 help=tr('metric.p_help'))
        interval = result.hac.confidence_interval_per_decade
        c.metric(tr('metric.ci'), tr('common.unavailable') if interval is None else tr("common.interval", low=interval[0], high=interval[1]),
                 help=tr('metric.ci_help'))
        a, b, c = st.columns(3)
        a.metric(tr('metric.r2'), tr('common.unavailable') if result.r_squared is None else f"{result.r_squared:.3f}",
                 help=tr('metric.r2_help'))
        b.metric(tr('metric.difference'), f"{result.first_to_last_difference:+.3f} °C",
                 help=tr('metric.difference_help'))
        c.metric(tr('metric.years'), str(len(result.years)))
    with st.container(border=True):
        st.subheader(tr("explore.temperature_" + frequency))
        st.plotly_chart(temperature_figure(period, frequency, show_trend, color=color, lang=lang),
                        width="stretch", key="explore_temperatures", config=chart_config(lang))
        if frequency == "Monthly":
            st.caption(tr('explore.monthly_caption'))
        else:
            st.caption(tr('explore.annual_caption'))
        if len(period.annual) != len(period.complete_annual):
            st.caption(tr('explore.incomplete'))
    st.subheader(tr('explore.meaning'))
    if result is not None:
        st.markdown(interpret_trend(result, lang=lang))
        if len(result.years) < 10:
            st.warning(tr('common.short_period'))
    else:
        st.write(tr('explore.no_trend'))
    with st.expander(tr('explore.diagnostics')):
        if result is not None:
            st.markdown(tr("explore.uncertainty", years=len(result.years), lags=plural("count.annual_lag", result.hac_lags, lang)))
            st.dataframe([
                {tr('column.method'): method,
                 tr('column.ci'): (
                     tr("common.interval_precise", low=inference.confidence_interval_per_decade[0], high=inference.confidence_interval_per_decade[1])
                     if inference.confidence_interval_per_decade is not None else tr('common.unavailable')),
                 tr('metric.p'): inference.p_value}
                for method, inference in ((tr('method.ols'), result.ols), (tr('method.hac'), result.hac))
            ], hide_index=True)
            d = result.diagnostics
            st.markdown(tr('explore.residuals'))
            st.dataframe([
                {tr('column.diagnostic'): tr('diagnostic.lag1'), tr('column.value'): d.lag1_correlation},
                {tr('column.diagnostic'): tr('diagnostic.dw'), tr('column.value'): d.durbin_watson},
                {tr('column.diagnostic'): tr('diagnostic.lb'), tr('column.value'): d.ljung_box_p_value},
                {tr('column.diagnostic'): tr('diagnostic.rmse'), tr('column.value'): d.rmse},
            ], hide_index=True)
            if d.autocorrelation_detected:
                st.info(tr('explore.dependence'))
            elif d.autocorrelation_detected is False:
                st.caption(tr('explore.no_dependence'))
            else:
                st.caption(tr('explore.unknown_dependence'))
            if d.potential_outlier_years or d.influential_years:
                unusual = ", ".join(str(year) for year in d.potential_outlier_years) or tr('common.none_flagged')
                influential = ", ".join(str(year) for year in d.influential_years) or tr('common.none_flagged')
                st.caption(tr("explore.influence", unusual=unusual, influential=influential))
        st.markdown(tr('explore.selection_data'))
        st.dataframe(display_temperature_data(period, frequency, lang=lang), hide_index=True)
        st.download_button(
            tr('explore.download'), processed_csv(period, frequency),
            file_name=f"terrashift_{country.lower()}_{frequency.lower()}_{start}_{end}.csv", mime="text/csv",
            on_click="ignore", key="download_data",
        )
        st.caption(tr('explore.download_caption'))


def render_methodology(registry_path, lang="en", dataset=None):
    tr = partial(t, lang=lang)
    st.subheader(tr('methodology.about'))
    if dataset is not None:
        st.caption(tr('coverage.summary', **coverage_labels(dataset, lang)))
        if source_request_notice(dataset, lang):
            st.caption(source_request_notice(dataset, lang))
    st.markdown(tr('methodology.about_text'))
    st.subheader(tr('methodology.pipeline'))
    st.markdown(tr('methodology.pipeline_text'))
    st.subheader(tr('methodology.reading'))
    st.markdown(tr('methodology.reading_text'))
    st.subheader(tr('methodology.sources'))
    st.write(tr('methodology.provenance'))
    registry = read_country_mapping(registry_path)
    st.dataframe([{tr('column.country'): country_name(name, lang), tr('column.source'): tr('source.nasa')}
                  for name in registry], hide_index=True)
    with st.expander(tr('methodology.technical')):
        st.markdown(tr('methodology.technical_text'))
        st.dataframe([{tr('column.country'): country_name(name, lang), tr('column.boundary'): entry["shape_identifier"]}
                      for name, entry in registry.items()], hide_index=True)
    st.markdown(tr('methodology.links'))


def render_compare(selected, start, end, frequency, colors, lang="en"):
    tr = partial(t, lang=lang)
    st.subheader(tr("compare.heading", start=start, end=end))
    if len(selected) < 2:
        st.info(tr('compare.empty'))
        return
    try:
        periods = analysis_value("compare", (tuple(selected), start, end), lambda: prepare_comparison(
            selected, start, end, mapping_path=ROOT / "metadata/country_mapping.json",
            raw_directory=ROOT / "data/raw"))
    except (ValueError, OSError):
        LOGGER.exception("Unable to prepare the selected country comparison")
        st.error(tr('error.comparison'))
        return
    st.subheader(tr("compare.temperature_" + frequency))
    if any(len(period.annual) != len(period.complete_annual) for period in periods.values()):
        st.caption(tr('compare.annual_complete'))
    st.plotly_chart(comparison_temperature_figure(periods, frequency, colors, lang=lang),
                   width="stretch", config=chart_config(lang), key="comparison_temperatures")
    st.caption(tr('compare.levels'))
    if frequency == "Monthly":
        st.caption(tr('compare.monthly_caption'))
    for country, period in periods.items():
        if period.analysis_notice:
            st.info(tr("compare.country_notice", country=country_name(country, lang), notice=localize_notice(period.analysis_notice, lang)))
    st.subheader(tr('compare.trends'))
    if any(period.trend is not None for period in periods.values()):
        st.plotly_chart(warming_rate_figure(periods, colors, lang=lang), width="stretch",
                       config=chart_config(lang), key="comparison_rates")
        st.caption(tr('compare.whiskers'))
    else:
        st.info(tr('compare.insufficient'))
    st.subheader(tr('compare.estimates'))
    st.dataframe(comparison_table(periods, lang=lang), hide_index=True, column_config={
        tr('column.trend'): st.column_config.NumberColumn(format="%.4f"),
        tr('metric.p'): st.column_config.NumberColumn(format="%.6g"),
        tr('column.r2'): st.column_config.NumberColumn(tr('metric.r2'), format="%.4f",
                                            help=tr('compare.r2_help')),
    })
    st.subheader(tr('compare.meaning'))
    st.markdown(interpret_comparison(periods, lang=lang))
    if end - start + 1 < 10:
        st.warning(tr('common.short_period'))


def main():
    with st.sidebar:
        lang = st.selectbox(t("sidebar.language", st.session_state.get("language", "en")),
                            list(LANGUAGES), format_func=LANGUAGES.get, key="language")
    tr = partial(t, lang=lang)
    begin_presentation(lang, ROOT)
    st.set_page_config(page_title=tr("app.page_title"), page_icon="🌎", layout="wide")
    st.caption(tr('app.challenge'))
    st.title(tr('app.title'))
    st.header(tr('app.heading'))
    st.write(tr('app.intro'))
    registry_path = ROOT / "metadata/country_mapping.json"
    try:
        countries = available_countries(registry_path)
        if not countries:
            raise ValueError("No resolved country entries are available.")
        colors = country_colors(countries)
    except (ValueError, OSError):
        LOGGER.exception("Unable to read the country registry")
        st.error(tr('error.registry'))
        st.stop()
    with st.sidebar:
        st.title(tr('sidebar.brand'))
        st.caption(tr('sidebar.caption'))
        country = st.selectbox(tr('sidebar.country'), countries,
                               index=countries.index("Peru") if "Peru" in countries else 0, key="country", format_func=partial(country_name, lang=lang))
        selected = st.multiselect(tr('sidebar.compare'), countries, default=[],
                                 max_selections=5, key="compare_countries", format_func=partial(country_name, lang=lang),
                                 placeholder=tr("sidebar.compare_placeholder"))
    try:
        dataset = analysis_value("country", (country,), lambda: load_country(
            country, mapping_path=registry_path, raw_directory=ROOT / "data/raw"))
    except (ValueError, OSError, KeyError):
        LOGGER.exception("Unable to load temperature data for %s", country)
        st.error(tr("error.country", country=country_name(country, lang)))
        st.info(tr('error.country_retry'))
        st.stop()
    st.caption(tr("coverage.summary", **coverage_labels(dataset, lang)))
    years = sorted(int(year) for year in dataset.monthly.date.dt.year.unique())
    with st.sidebar:
        st.subheader(tr('sidebar.period'))
        start = st.selectbox(tr('sidebar.start'), years, index=0, key="start_year")
        end = st.selectbox(tr('sidebar.end'), years, index=len(years) - 1, key="end_year")
        frequency = st.radio(tr('sidebar.frequency'), ["Annual", "Monthly"], key="frequency",
                             format_func=lambda value: tr("frequency." + value))
        show_trend = st.toggle(tr('sidebar.trend_toggle'), value=True,
                               disabled=frequency == "Monthly", key="show_trend")
        st.caption(tr('sidebar.scope'))
        st.divider()
        st.markdown(tr('sidebar.source', **coverage_labels(dataset, lang)))
    st.divider()
    if start > end:
        st.warning(tr('error.period'))
        st.stop()
    explore, compare, methodology = localized_tabs(lang)
    with explore:
        render_map(country, start, end, registry_path, lang=lang)
        render_explore(dataset, country, start, end, frequency, show_trend, colors[country], lang=lang)
    with compare:
        render_compare(selected, start, end, frequency, colors, lang=lang)
    with methodology:
        render_methodology(registry_path, lang=lang, dataset=dataset)
    st.divider()
    st.caption(tr('app.footer'))


if __name__ == "__main__":
    main()
