"""Selection, chart semantics, downloads, and Streamlit runtime interactions."""

from io import BytesIO
from pathlib import Path
import json
import shutil
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core.data_loader import load_data, resolve_reference_source
from core.data_cleaning import clean_monthly
from core.dashboard_data import prepare_period, processed_csv, interpret_trend
from core.dashboard_charts import temperature_figure
from core.trend_analysis import analyze_annual_trend

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def monthly():
    return clean_monthly(load_data(resolve_reference_source()).observations)


def test_full_period_reference_results(monthly):
    period = prepare_period(monthly, 2000, 2025)
    result = period.trend
    assert len(period.monthly) == 312
    assert len(period.complete_annual) == 26
    assert result.slope_per_decade == pytest.approx(.370206, abs=1e-6)
    assert result.hac.confidence_interval_per_decade == pytest.approx((.132071, .608341), abs=1e-6)
    assert result.hac.p_value == pytest.approx(.003762, abs=1e-6)
    assert result.r_squared == pytest.approx(.377904, abs=1e-6)


def test_selected_period_recalculates_without_mutation(monthly):
    original = monthly.copy(deep=True)
    period = prepare_period(monthly, 2010, 2020)
    expected = analyze_annual_trend(period.complete_annual)
    assert period.monthly.date.min() == pd.Timestamp("2010-01-01")
    assert period.monthly.date.max() == pd.Timestamp("2020-12-01")
    assert len(period.monthly) == 132
    assert period.trend == expected
    assert period.trend.slope_per_decade != prepare_period(monthly, 2000, 2025).trend.slope_per_decade
    pd.testing.assert_frame_equal(monthly, original)


@pytest.mark.parametrize("start,end", [(2000, 2000), (2024, 2025), (1990, 1999)])
def test_short_or_empty_period_has_data_without_inference(monthly, start, end):
    period = prepare_period(monthly, start, end)
    assert period.trend is None
    assert period.analysis_notice
    if start >= 2000:
        assert len(period.monthly) == (end - start + 1) * 12


@pytest.mark.parametrize("start,end", [(2025, 2000), (2000.5, 2025), (True, 2025)])
def test_invalid_period(monthly, start, end):
    with pytest.raises(ValueError):
        prepare_period(monthly, start, end)


def test_incomplete_year_does_not_erase_monthly_data(monthly):
    selected = monthly.loc[monthly.date.dt.year.between(2000, 2004)].copy()
    selected.loc[selected.date.eq(pd.Timestamp("2002-01-01")), ["temperature_k", "temperature_c"]] = float("nan")
    period = prepare_period(selected, 2000, 2004)
    assert len(period.monthly) == 60
    assert len(period.complete_annual) == 4
    assert not period.annual.loc[period.annual.year.eq(2002), "is_complete"].iloc[0]
    assert period.trend is None  # Existing inference rejects gaps, not irregular HAC lags.
    assert "consecutive" in period.analysis_notice


@pytest.mark.parametrize("frequency", ["Annual", "Monthly"])
def test_csv_download_matches_selection(monthly, frequency):
    period = prepare_period(monthly, 2010, 2012)
    table = pd.read_csv(BytesIO(processed_csv(period, frequency)))
    assert len(table) == (3 if frequency == "Annual" else 36)
    assert "temperature_c" in table
    if frequency == "Annual":
        assert table.year.tolist() == [2010, 2011, 2012]
        assert table.is_complete.all()
    else:
        assert table.date.iloc[0] == "2010-01-01"
        assert table.date.iloc[-1] == "2012-12-01"


def test_charts_show_only_annual_regression(monthly):
    period = prepare_period(monthly, 2000, 2025)
    annual = temperature_figure(period, "Annual", True)
    assert len(annual.data) == 2
    assert list(annual.data[1].y) == list(period.trend.fitted_values)
    assert len(temperature_figure(period, "Annual", False).data) == 1
    monthly_chart = temperature_figure(period, "Monthly", True)
    assert len(monthly_chart.data) == 1
    assert len(monthly_chart.data[0].y) == 312
    assert list(monthly_chart.data[0].y) == period.monthly.temperature_c.tolist()
    assert "°C" in monthly_chart.layout.yaxis.title.text
    assert len(temperature_figure(prepare_period(monthly, 2000, 2000), "Annual").data) == 1


def test_invalid_frequency_is_rejected(monthly):
    period = prepare_period(monthly, 2000, 2025)
    for function in (processed_csv, temperature_figure):
        with pytest.raises(ValueError, match="Frequency"):
            function(period, "Daily")


def test_interpretation_tracks_selected_range_and_assumptions(monthly):
    result = prepare_period(monthly, 2010, 2020).trend
    text = interpret_trend(result)
    assert "2010 to 2020" in text
    assert f"{result.slope_per_decade:+.3f}" in text
    assert "confidence interval" in text
    assert "first-to-last" in text


@pytest.mark.parametrize("values,expected", [([20.] * 10, "unavailable"),
                                          ([20., 21., 19., 20., 21., 19., 20., 21., 19., 20.], "direction of change remains uncertain")])
def test_interpretation_degenerate_and_uncertain(values, expected):
    result = analyze_annual_trend(pd.DataFrame({"year": range(2000, 2010), "temperature_c": values}))
    assert expected in interpret_trend(result)


def test_streamlit_default_runtime_and_controls():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert not app.error
    assert app.metric[0].value == "+0.370 °C/decade"
    app.selectbox(key="start_year").set_value(2010).run()
    assert not app.exception
    assert app.metric[-1].value == "16"
    assert app.metric[0].value != "+0.370 °C/decade"
    app.radio(key="frequency").set_value("Monthly").run()
    assert not app.exception
    assert app.toggle(key="show_trend").disabled
    assert "Monthly average temperature" in [element.value for element in app.subheader]
    app.radio(key="frequency").set_value("Annual").run()
    app.toggle(key="show_trend").set_value(False).run()
    assert not app.exception
    app.selectbox(key="start_year").set_value(2025).run()
    assert not app.exception
    assert not app.metric
    assert app.info
    app.selectbox(key="end_year").set_value(2024).run()
    assert not app.exception
    assert any("Start year" in warning.value for warning in app.warning)


def test_dashboard_reports_registry_load_error():
    from core.region_data import RegionDataError
    with patch("core.region_data.load_country", side_effect=RegionDataError("Peru: source file missing")):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert any("Temperature data for Peru is temporarily unavailable" in error.value for error in app.error)
    assert not app.metric


def test_dashboard_resolves_registry_filename_after_rename(tmp_path):
    # Only the temporary fixture is renamed; repository raw files stay untouched.
    shutil.copyfile(ROOT / "app.py", tmp_path / "app.py")
    (tmp_path / "metadata").mkdir()
    (tmp_path / "data/raw").mkdir(parents=True)
    registry = json.loads((ROOT / "metadata/country_mapping.json").read_text())
    peru = next(entry for entry in registry["countries"] if entry["country"] == "Peru")
    peru["filename"] = "renamed-peru.csv"
    (tmp_path / "metadata/country_mapping.json").write_text(json.dumps(registry))
    shutil.copyfile(resolve_reference_source(), tmp_path / "data/raw/renamed-peru.csv")
    # No legacy dataset_provenance.json or hardcoded NASA filename is present.
    app = AppTest.from_file(str(tmp_path / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert not app.error
    assert app.metric[0].value == "+0.370 °C/decade"
