"""Compare actual registry data and predictable synthetic trends, without modifying raw files."""

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core import country_comparison
from core.country_comparison import (available_countries, country_colors, prepare_comparison,
                                     comparison_table, interpret_comparison)
from core.dashboard_data import prepare_period
from core.dashboard_charts import comparison_temperature_figure, warming_rate_figure, temperature_figure
from core.region_data import load_country, read_country_mapping

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def comparison():
    return prepare_comparison(["Peru", "Brazil"], 2010, 2020)


def test_country_options_and_stable_colors_come_from_registry():
    names = available_countries()
    assert names == sorted(read_country_mapping())
    colors = country_colors(names)
    assert colors == country_colors(list(reversed(names)))
    assert len(set(colors.values())) == 12
    with pytest.raises(ValueError, match="12"):
        country_colors([f"country{i}" for i in range(13)])


def test_pending_registry_entry_is_not_selectable(tmp_path):
    registry = json.loads((ROOT / "metadata/country_mapping.json").read_text())
    registry["countries"][0]["status"] = "pending_confirmation"
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(registry))
    assert registry["countries"][0]["country"] not in available_countries(path)


def test_multi_country_loading_and_period_reuses_existing_pipeline():
    with patch.object(country_comparison, "prepare_period", wraps=prepare_period) as prepare:
        result = prepare_comparison(["Peru", "Brazil"], 2010, 2020)
    assert prepare.call_count == 2
    for country, period in result.items():
        expected = prepare_period(load_country(country).monthly, 2010, 2020)
        pd.testing.assert_frame_equal(period.monthly, expected.monthly)
        assert period.trend == expected.trend
        assert len(period.monthly) == 132
        assert period.monthly.date.min() == pd.Timestamp("2010-01-01")
        assert period.monthly.date.max() == pd.Timestamp("2020-12-01")
        assert len(period.complete_annual) == 11
        assert period.monthly.country.eq(country).all()


@pytest.mark.parametrize("countries", [[], ["Peru"], available_countries()[:6],
                                      ["Peru", "Peru"], ["Peru", "Atlantis"], ["Peru", None]])
def test_invalid_comparison_selection(countries):
    with pytest.raises(ValueError):
        prepare_comparison(countries, 2000, 2025)


def test_five_countries_supported():
    result = prepare_comparison(available_countries()[:5], 2000, 2025)
    assert len(result) == 5
    assert all(len(period.complete_annual) == 26 for period in result.values())


@pytest.mark.parametrize("start,end", [(2025, 2000), (2000.5, 2020)])
def test_invalid_period_is_not_silently_changed(start, end):
    with pytest.raises(ValueError):
        prepare_comparison(["Peru", "Brazil"], start, end)


@pytest.mark.parametrize("frequency,points", [("Annual", 11), ("Monthly", 132)])
def test_temperature_comparison_uses_actual_selected_values(comparison, frequency, points):
    colors = country_colors(available_countries())
    figure = comparison_temperature_figure(comparison, frequency, colors)
    assert [trace.name for trace in figure.data] == ["Peru", "Brazil"]
    for trace in figure.data:
        period = comparison[trace.name]
        frame = period.annual if frequency == "Annual" else period.monthly
        assert len(trace.y) == points
        assert list(trace.y) == frame.temperature_c.tolist()
        assert trace.line.color == colors[trace.name]
        assert trace.connectgaps is False
    assert "°C" in figure.layout.yaxis.title.text
    reordered = comparison_temperature_figure(dict(reversed(list(comparison.items()))), frequency, colors)
    assert {trace.name: trace.line.color for trace in figure.data} == {trace.name: trace.line.color for trace in reordered.data}
    detail = temperature_figure(comparison["Peru"], frequency, color=colors["Peru"])
    assert detail.data[0].line.color == figure.data[0].line.color


def test_temperature_chart_rejects_invalid_frequency(comparison):
    with pytest.raises(ValueError, match="Frequency"):
        comparison_temperature_figure(comparison, "Daily", country_colors(available_countries()))


def test_comparison_chart_preserves_missing_values(comparison):
    first_index = comparison["Peru"].monthly.index[0]
    comparison["Peru"].monthly.loc[first_index, "temperature_c"] = np.nan
    figure = comparison_temperature_figure(comparison, "Monthly", country_colors(available_countries()))
    assert pd.isna(figure.data[0].y[0])
    assert figure.data[0].connectgaps is False


def test_rate_chart_whiskers_hover_and_individual_significance(comparison):
    figure = warming_rate_figure(comparison, country_colors(available_countries()))
    assert len(figure.data) == 2
    for trace in figure.data:
        result = comparison[trace.name].trend
        lower, upper = result.hac.confidence_interval_per_decade
        assert trace.orientation == "h"
        assert trace.x[0] == result.slope_per_decade
        assert trace.x[0] + trace.error_x.array[0] == pytest.approx(upper)
        assert trace.x[0] - trace.error_x.arrayminus[0] == pytest.approx(lower)
        assert trace.customdata[0][0] == f"[{lower:+.6f}, {upper:+.6f}]"
        assert trace.customdata[0][1] == f"{result.hac.p_value:.6g}"
        assert trace.customdata[0][2] == "2010–2020"
        assert trace.text[0] == ("*" if result.hac.significant else "Not significant")
    assert figure.layout.shapes[0].x0 == figure.layout.shapes[0].x1 == 0


def test_comparison_table_contains_existing_inference(comparison):
    table = comparison_table(comparison).set_index("Country")
    for country, period in comparison.items():
        result = period.trend
        row = table.loc[country]
        assert row["Years analyzed"] == 11
        assert row["Analysis period"] == "2010–2020"
        assert row["Trend (°C/decade)"] == result.slope_per_decade
        assert row["Trend p-value"] == result.hac.p_value
        assert row["R²"] == result.r_squared
        lo, hi = result.hac.confidence_interval_per_decade
        assert row["95% confidence interval (°C/decade)"] == f"{lo:+.3f} to {hi:+.3f}"


def test_short_period_keeps_temperatures_and_unavailable_rows():
    result = prepare_comparison(["Peru", "Brazil"], 2024, 2025)
    assert all(period.trend is None for period in result.values())
    table = comparison_table(result)
    assert table["Trend (°C/decade)"].isna().all()
    assert table["Trend significance"].eq("Unavailable").all()
    assert table["Years analyzed"].eq(2).all()
    colors = country_colors(available_countries())
    assert len(warming_rate_figure(result, colors).data) == 0
    assert all(len(trace.y) == 24 for trace in comparison_temperature_figure(result, "Monthly", colors).data)


def synthetic_period(values):
    dates = pd.date_range("2000-01-01", periods=12 * len(values), freq="MS")
    monthly = pd.DataFrame({"date": dates, "temperature_c": np.repeat(values, 12)})
    monthly["temperature_k"] = monthly.temperature_c + 273.15
    return prepare_period(monthly, 2000, 2000 + len(values) - 1)


def test_dynamic_interpretation_positive_negative_and_unavailable():
    noise = np.sin(np.arange(10)) * .01
    periods = {"Positive": synthetic_period(20 + .2 * np.arange(10) + noise),
               "Negative": synthetic_period(20 - .2 * np.arange(10) + noise),
               "Constant": synthetic_period(np.full(10, 20.))}
    text = interpret_comparison(periods)
    assert "Estimated warming: **Positive**" in text
    assert "Estimated cooling: **Negative**" in text
    assert "Statistical evidence of an individual trend: **Positive, Negative**" in text
    assert "Trend uncertainty cannot be assessed for **Constant**" in text
    assert "does not test whether their rates of change differ statistically" in text
    assert "rather than what caused them" in text
    figure = warming_rate_figure(periods, {name: color for name, color in zip(periods, ["red", "blue", "green"])})
    assert figure.data[2].text[0] == "Not assessed"
    assert not figure.data[2].error_x.array


def test_nonsignificant_interpretation_does_not_claim_no_change():
    period = synthetic_period([20., 21., 19., 20., 21., 19., 20., 21., 19., 20.])
    assert period.trend.hac.significant is False
    assert "does not mean temperatures stayed the same" in interpret_comparison({"Uncertain": period})


def test_streamlit_country_selection_and_comparison_interactions():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Explore", "Compare", "Methodology"]
    assert app.selectbox(key="country").value == "Peru"
    assert len(app.selectbox(key="country").options) == 12
    app.selectbox(key="country").set_value("Brazil").run()
    assert not app.exception and not app.error
    expected = prepare_period(load_country("Brazil").monthly, 2000, 2025).trend
    assert app.metric[0].value == f"{expected.slope_per_decade:+.3f} °C/decade"
    app.multiselect(key="compare_countries").set_value(["Peru", "Brazil", "Chile"]).run()
    assert not app.exception and not app.error
    table = next(frame.value for frame in app.dataframe if "Country" in frame.value and "Trend p-value" in frame.value)
    assert table.Country.tolist() == ["Peru", "Brazil", "Chile"]
    app.selectbox(key="start_year").set_value(2010).run()
    app.selectbox(key="end_year").set_value(2020).run()
    assert not app.exception and not app.error
    table = next(frame.value for frame in app.dataframe if "Country" in frame.value and "Trend p-value" in frame.value)
    assert table["Years analyzed"].eq(11).all()
    assert table["Analysis period"].eq("2010–2020").all()
    app.radio(key="frequency").set_value("Monthly").run()
    assert not app.exception and not app.error
    assert any("Monthly average temperatures" == subheader.value for subheader in app.subheader)
    app.selectbox(key="start_year").set_value(2020).run()
    assert not app.exception and not app.error
    table = next(frame.value for frame in app.dataframe if "Country" in frame.value and "Trend p-value" in frame.value)
    assert table["Trend (°C/decade)"].isna().all()
    assert any("at least three" in element.value for element in app.info)
    app.multiselect(key="compare_countries").set_value(["Peru"]).run()
    assert not app.exception
    assert any("Select 2–5" in element.value for element in app.info)
