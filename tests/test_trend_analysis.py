"""Predictable synthetic checks plus integration with the unmodified NASA CSV."""

import hashlib

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from core.data_loader import load_data, resolve_reference_source
from core.data_cleaning import clean_monthly, annual_mean_temperatures, annual_trend_ready
from core.trend_analysis import analyze_annual_trend, newey_west_covariance, select_hac_lags


def annual(values, start=2000):
    return pd.DataFrame({"year": np.arange(start, start + len(values)), "temperature_c": values})


@pytest.mark.parametrize("slope", [0.1, -0.2])
def test_known_exact_linear_trends(slope):
    frame = annual(20 + slope * np.arange(26))
    result = analyze_annual_trend(frame)
    assert result.slope_per_year == pytest.approx(slope)
    assert result.slope_per_decade == pytest.approx(slope * 10)
    assert result.intercept == pytest.approx(20 - slope * 2000)
    assert result.r_squared == pytest.approx(1)
    assert result.first_to_last_difference == pytest.approx(25 * slope)
    assert result.ols.p_value is None  # Zero residual variance is degenerate.
    assert result.hac.confidence_interval is None


def test_constant_series():
    result = analyze_annual_trend(annual(np.full(26, 20.0)))
    assert result.slope_per_year == 0
    assert result.intercept == 20
    assert result.r_squared is None
    assert result.first_to_last_difference == 0
    assert result.ols.significant is None
    assert result.diagnostics.durbin_watson is None


@pytest.mark.parametrize("n", [0, 1, 2])
def test_insufficient_observations(n):
    with pytest.raises(ValueError, match="At least three"):
        analyze_annual_trend(annual(np.arange(n)))


@pytest.mark.parametrize("column", ["year", "temperature_c"])
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf, "invalid", pd.NA])
def test_missing_nonfinite_and_nonnumeric(column, value):
    frame = annual(np.arange(10)).astype(object)
    frame.loc[3, column] = value
    with pytest.raises(ValueError, match="finite"):
        analyze_annual_trend(frame)


@pytest.mark.parametrize("years", [[2000, 2000, 2002], [2002, 2001, 2000], [2000, 2001, 2003], [2000, 2001.5, 2002]])
def test_invalid_calendar_years(years):
    with pytest.raises(ValueError, match="consecutive"):
        analyze_annual_trend(pd.DataFrame({"year": years, "temperature_c": [1., 2., 4.]}))


def test_incomplete_years_rejected():
    frame = annual([1., 2., 4.])
    frame["is_complete"] = [True, False, True]
    with pytest.raises(ValueError, match="complete years"):
        analyze_annual_trend(frame)


def test_missing_columns():
    with pytest.raises(ValueError, match="columns"):
        analyze_annual_trend(pd.DataFrame({"wrong": [1, 2, 3]}))


def test_confidence_interval_and_p_value_known_small_example():
    # x = 0,1,2,3,4; y = 1,2,1,3,3: slope=.5, Sxx=10, SSE=1.5.
    result = analyze_annual_trend(annual([1., 2., 1., 3., 3.]))
    se = np.sqrt(0.5 / 10)
    assert result.slope_per_year == pytest.approx(0.5)
    assert result.ols.standard_error == pytest.approx(se)
    # t(.975,3)=3.182446305284263, independently tabulated critical value.
    expected = (0.5 - 3.182446305284263 * se, 0.5 + 3.182446305284263 * se)
    assert result.ols.confidence_interval == pytest.approx(expected)
    assert result.ols.confidence_interval_per_decade == pytest.approx(np.array(expected) * 10)
    assert result.ols.p_value == pytest.approx(0.1113671547140838)
    assert not result.ols.significant
    assert result.r_squared == pytest.approx(0.625)


@pytest.mark.parametrize("slope", [-0.05, 0.05])
def test_noisy_slope_matches_scipy(slope):
    rng = np.random.default_rng(16)
    frame = annual(20 + slope * np.arange(26) + rng.normal(0, 0.05, 26))
    original = frame.copy(deep=True)
    result = analyze_annual_trend(frame)
    reference = stats.linregress(frame.year, frame.temperature_c)
    assert result.slope_per_year == pytest.approx(reference.slope)
    assert result.intercept == pytest.approx(reference.intercept)
    assert result.ols.standard_error == pytest.approx(reference.stderr)
    assert result.ols.p_value == pytest.approx(reference.pvalue)
    assert result.ols.significant
    assert result.r_squared == pytest.approx(reference.rvalue ** 2)
    pd.testing.assert_frame_equal(frame, original)


def test_hac_against_independent_scalar_sandwich():
    values = [2., 4., 3., 6., 5., 4., 8., 7.]
    frame = annual(values)
    result = analyze_annual_trend(frame, hac_lags=2)
    # With centered x, slope score is x_i*e_i and slope bread is 1/Sxx.
    x = np.arange(8) - 3.5
    e = np.array(values) - np.array(result.fitted_values)
    scores = x * e
    meat = sum(score ** 2 for score in scores)
    for lag in (1, 2):
        meat += 2 * (1 - lag / 3) * sum(scores[i] * scores[i-lag] for i in range(lag, 8))
    expected_se = np.sqrt((8 / 6) * meat / sum(x ** 2) ** 2)
    assert result.hac.standard_error == pytest.approx(expected_se)
    critical = stats.t.ppf(.975, 6)
    assert result.hac.confidence_interval == pytest.approx((result.slope_per_year - critical * expected_se, result.slope_per_year + critical * expected_se))
    assert result.hac.p_value == pytest.approx(2 * stats.t.sf(abs(result.slope_per_year / expected_se), 6))
    assert result.hac.significant == (result.hac.p_value < .05)
    assert result.hac_lags == 2


def test_hac_lag_zero_is_corrected_white_covariance():
    x = np.column_stack((np.ones(6), np.arange(6) - 2.5))
    residuals = np.array([1., -1., 0., 2., -2., 0.])
    inv = np.linalg.inv(x.T @ x)
    expected = (6 / 4) * inv @ x.T @ np.diag(residuals ** 2) @ x @ inv
    np.testing.assert_allclose(newey_west_covariance(x, residuals, 0), expected, atol=1e-14)
    assert analyze_annual_trend(annual([1., 2., 1., 3., 4., 2.]), hac_lags=0).hac_lags == 0


def test_default_lag_rule():
    assert select_hac_lags(26) == 2
    assert select_hac_lags(3) < 3


@pytest.mark.parametrize("lag", [-1, 26, 1.5, True, "2"])
def test_invalid_hac_lags(lag):
    with pytest.raises(ValueError, match="HAC lags"):
        analyze_annual_trend(annual(np.arange(26)), hac_lags=lag)


def test_autocorrelation_screen_and_residual_behavior():
    frame = annual(20 + .03 * np.arange(80) + np.sin(np.arange(80) / 5))
    result = analyze_annual_trend(frame)
    d = result.diagnostics
    assert d.autocorrelation_detected
    assert d.lag1_correlation > .8
    assert d.durbin_watson < .5
    assert abs(d.residual_mean) < 1e-12
    assert d.rmse > 0
    assert any("naive OLS" in warning for warning in result.warnings)


def test_outlier_flags_do_not_remove_observations():
    values = 20 + .02 * np.arange(26) + .01 * np.sin(np.arange(26))
    values[13] += 3
    result = analyze_annual_trend(annual(values))
    assert 2013 in result.diagnostics.potential_outlier_years
    assert 2013 in result.diagnostics.influential_years
    assert len(result.temperatures_c) == 26


def test_nasa_pipeline_integration():
    loaded = load_data(resolve_reference_source())
    before = hashlib.sha256(loaded.source.read_bytes()).hexdigest()
    complete = annual_trend_ready(annual_mean_temperatures(clean_monthly(loaded.observations)))
    result = analyze_annual_trend(complete)
    assert len(result.years) == 26
    assert result.years[0] == 2000 and result.years[-1] == 2025
    reference = stats.linregress(complete.year, complete.temperature_c)
    assert result.slope_per_year == pytest.approx(reference.slope)
    assert result.first_to_last_difference == pytest.approx(complete.temperature_c.iloc[-1] - complete.temperature_c.iloc[0])
    assert result.hac_lags == 2
    assert np.isfinite(result.hac.p_value)
    assert result.hac.confidence_interval[0] < result.slope_per_year < result.hac.confidence_interval[1]
    assert hashlib.sha256(loaded.source.read_bytes()).hexdigest() == before
