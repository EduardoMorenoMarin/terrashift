"""Public wording, scientific distinctions and protection against metadata leakage."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core.country_comparison import interpret_comparison
from core.dashboard_copy import display_temperature_data
from core.dashboard_data import interpret_trend, prepare_period
from core.dashboard_charts import temperature_figure, warming_rate_figure
from core.region_data import load_country, RegionDataError
from core.trend_analysis import analyze_annual_trend

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_WORDING = (
    "user_confirmed", "user_reported", "independently_verified", "pending_confirmation",
    "user-confirmed", "user-reported", "not independently verified", "bounding boxes",
    "unsupported", "no direct tests", "registry", "checksum", "sha256",
    "temperature_c", "temperature_k", "valid_months", "is_complete", "shape_identifier",
)


def rendered_public_text(app):
    """Include expanded content, tables, chart specs, labels, values and help text."""
    pieces = []
    for kind in ("title", "header", "subheader", "caption", "markdown", "text", "info",
                 "warning", "error", "metric", "selectbox", "multiselect", "radio",
                 "toggle", "button", "download_button", "tab", "expander"):
        for element in app.get(kind):
            for field in ("value", "label", "help"):
                try:
                    value = getattr(element, field)
                except (AttributeError, KeyError, NotImplementedError):
                    continue
                if isinstance(value, (str, list, tuple)):
                    pieces.append(str(value))
    pieces.extend(frame.value.to_json(date_format="iso") for frame in app.dataframe)
    pieces.extend(chart.proto.spec for chart in app.get("plotly_chart"))
    return "\n".join(pieces)


@pytest.mark.parametrize("country,start,end,frequency,comparison", [
    ("Peru", 2000, 2025, "Annual", ["Peru", "Brazil"]),
    ("Chile", 2010, 2020, "Monthly", ["Chile", "Bolivia", "Venezuela"]),
    ("Argentina", 2024, 2025, "Annual", ["Argentina", "Uruguay"]),
])
def test_all_tabs_use_public_copy(country, start, end, frequency, comparison):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.selectbox(key="country").set_value(country)
    app.selectbox(key="start_year").set_value(start)
    app.selectbox(key="end_year").set_value(end)
    app.radio(key="frequency").set_value(frequency)
    app.multiselect(key="compare_countries").set_value(comparison)
    app.run()
    assert not app.exception and not app.error
    text = rendered_public_text(app)
    assert not any(word in text.lower() for word in PRIVATE_WORDING)
    assert "reanalysis" in text.lower()
    assert "individual country boundary selections" in text
    assert "original Giovanni boundary references are retained for traceability" in text
    assert "rather than what caused" in text
    assert "95% confidence interval" in text
    assert "p-value" in text
    assert [tab.label for tab in app.tabs] == ["Explore", "Compare", "Methodology"]
    source_table = next(frame.value for frame in app.dataframe if "Data source" in frame.value)
    assert source_table.columns.tolist() == ["Country", "Data source"]
    assert len(source_table) == 12
    assert "Technical details" in [expander.label for expander in app.expander]
    assert any("Giovanni boundary reference" in frame.value for frame in app.dataframe)


@pytest.mark.parametrize("target", ["core.region_data.load_country",
                                   "core.country_comparison.available_countries",
                                   "core.country_comparison.prepare_comparison"])
def test_errors_hide_internal_metadata_and_paths(target):
    message = "user_confirmed unsupported registry /private/source.csv checksum mismatch"
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.multiselect(key="compare_countries").set_value(["Peru", "Brazil"])
    with patch(target, side_effect=RegionDataError(message)):
        app.run()
    assert not app.exception
    assert app.error
    text = rendered_public_text(app)
    assert "/private/source.csv" not in text
    assert not any(word in text.lower() for word in PRIVATE_WORDING)


@pytest.mark.parametrize("frequency", ["Annual", "Monthly"])
def test_display_table_labels_leave_source_data_unchanged(frequency):
    period = prepare_period(load_country("Peru").monthly, 2000, 2002)
    original = (period.annual if frequency == "Annual" else period.monthly).copy(deep=True)
    public = display_temperature_data(period, frequency)
    assert "Temperature (°C)" in public
    assert "Temperature (K)" in public
    assert not any("_" in label for label in public.columns)
    if frequency == "Annual":
        assert public["Complete year"].eq("Yes").all()
    pd.testing.assert_frame_equal(period.annual if frequency == "Annual" else period.monthly, original)


@pytest.mark.parametrize("values,expected", [
    (20 + .2 * np.arange(10) + np.sin(np.arange(10)) * .01, "indicating warming"),
    (20 - .2 * np.arange(10) + np.sin(np.arange(10)) * .01, "indicating cooling"),
    (np.full(10, 20.), "no estimated linear change"),
    ([20., 21., 19., 20., 21., 19., 20., 21., 19., 20.], "direction of change remains uncertain"),
])
def test_trend_summaries_cover_each_result_type(values, expected):
    result = analyze_annual_trend(pd.DataFrame({"year": range(2000, 2010), "temperature_c": values}))
    text = interpret_trend(result)
    assert expected in text
    assert "2000 to 2009" in text
    assert "first-to-last" in text
    assert "\n\n" in text
    assert not any(word in text.lower() for word in PRIVATE_WORDING)
    assert len(text.split()) < 180
    if result.hac.confidence_interval is not None:
        assert "95% confidence interval" in text
    else:
        assert "almost exact line" in text
        assert "p-values are unavailable" in text


def test_short_comparison_uses_neutral_and_grammatical_copy():
    period = prepare_period(load_country("Peru").monthly, 2025, 2025)
    text = interpret_comparison({"Peru": period})
    assert "Trend uncertainty cannot be assessed for **Peru**" in text
    assert "does not test whether their rates of change differ statistically" in text
    assert "Estimated warming" not in text
    assert not any(word in text.lower() for word in PRIVATE_WORDING)


def test_chart_labels_are_readable_and_preserve_uncertainty():
    period = prepare_period(load_country("Peru").monthly, 2000, 2025)
    temperatures = temperature_figure(period, "Annual")
    assert [trace.name for trace in temperatures.data] == ["Annual average", "Linear trend"]
    assert "Full year" in temperatures.data[0].hovertemplate
    assert temperatures.data[0].customdata[0][1] == "Yes"
    rate = warming_rate_figure({"Peru": period}, {"Peru": "teal"})
    assert "95% confidence interval" in rate.data[0].hovertemplate
    assert "Trend p-value" in rate.data[0].hovertemplate
    assert rate.data[0].customdata[0][3] == "Statistically significant"
