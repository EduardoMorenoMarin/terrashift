"""Annual linear trends with classical OLS and Bartlett/Newey–West inference.

HAC bandwidth: floor(4*(n/100)**(2/9)), capped at n-1 (2 for n=26).
The sandwich covariance uses n/(n-2) correction; both inference methods use
Student-t reference distributions with n-2 degrees of freedom. HAC inference
is approximate, particularly in short series. It does not change coefficients.
See https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html
"""

from dataclasses import dataclass
from numbers import Integral

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class SlopeInference:
    standard_error: float | None
    confidence_interval: tuple[float, float] | None
    p_value: float | None
    significant: bool | None

    @property
    def confidence_interval_per_decade(self) -> tuple[float, float] | None:
        if self.confidence_interval is None:
            return None
        return tuple(bound * 10 for bound in self.confidence_interval)


@dataclass(frozen=True)
class ResidualDiagnostics:
    lag1_correlation: float | None
    durbin_watson: float | None
    ljung_box_lags: int
    ljung_box_statistic: float | None
    ljung_box_p_value: float | None
    autocorrelation_detected: bool | None
    residual_mean: float
    residual_standard_deviation: float
    rmse: float
    max_absolute_residual: float
    standardized_residuals: tuple[float, ...] | None
    cooks_distance: tuple[float, ...] | None
    potential_outlier_years: tuple[int, ...]
    influential_years: tuple[int, ...]


@dataclass(frozen=True)
class TrendResult:
    years: tuple[int, ...]
    temperatures_c: tuple[float, ...]
    slope_per_year: float
    intercept: float
    r_squared: float | None
    first_to_last_difference: float
    fitted_values: tuple[float, ...]
    residuals: tuple[float, ...]
    ols: SlopeInference
    hac: SlopeInference
    hac_lags: int
    diagnostics: ResidualDiagnostics
    warnings: tuple[str, ...]
    alpha: float = 0.05

    @property
    def slope_per_decade(self) -> float:
        return self.slope_per_year * 10


def select_hac_lags(n: int) -> int:
    """Return the conventional sample-size bandwidth, not a fitted AR order."""
    if isinstance(n, bool) or not isinstance(n, Integral) or n < 3:
        raise ValueError("At least three observations are required for HAC inference.")
    return min(n - 1, int(np.floor(4 * (n / 100) ** (2 / 9))))


def newey_west_covariance(design: np.ndarray, residuals: np.ndarray, lags: int) -> np.ndarray:
    """Bartlett HAC sandwich for full-rank design; observations must be equally spaced.

    Includes the finite-sample n/(n-k) correction. lags=0 is a
    heteroskedasticity-only covariance, with no serial-correlation adjustment.
    """
    design = np.asarray(design, dtype=float)
    residuals = np.asarray(residuals, dtype=float)
    if design.ndim != 2 or residuals.shape != (design.shape[0],):
        raise ValueError("Design must be 2D and residuals must match its rows.")
    n, k = design.shape
    if n <= k or not np.isfinite(design).all() or not np.isfinite(residuals).all():
        raise ValueError("HAC requires finite inputs and positive residual degrees of freedom.")
    if np.linalg.matrix_rank(design) != k:
        raise ValueError("HAC design must have full column rank.")
    if isinstance(lags, bool) or not isinstance(lags, Integral) or not 0 <= lags < n:
        raise ValueError(f"HAC lags must be an integer between 0 and {n - 1}.")
    scores = design * residuals[:, None]
    meat = scores.T @ scores
    for lag in range(1, lags + 1):
        cross = scores[lag:].T @ scores[:-lag]
        meat += (1 - lag / (lags + 1)) * (cross + cross.T)
    bread = np.linalg.inv(design.T @ design)
    return (n / (n - k)) * bread @ meat @ bread


def _inference(slope: float, standard_error: float, df: int) -> SlopeInference:
    critical = stats.t.ppf(0.975, df)
    interval = (float(slope - critical * standard_error), float(slope + critical * standard_error))
    if standard_error == 0:
        return SlopeInference(0.0, None, None, None)
    p_value = float(2 * stats.t.sf(abs(slope / standard_error), df))
    return SlopeInference(standard_error, interval, p_value, p_value < 0.05)


def _diagnostics(years, residuals, design, degenerate) -> ResidualDiagnostics:
    n = len(residuals)
    sse = float(residuals @ residuals)
    mean = float(residuals.mean())
    std = float(residuals.std(ddof=1))
    rmse = float(np.sqrt(sse / n))
    maximum = float(np.max(np.abs(residuals)))
    lags = min(3, n - 2)
    if degenerate:
        return ResidualDiagnostics(None, None, lags, None, None, None,
                                   mean, std, rmse, maximum, None, None, (), ())
    left, right = residuals[:-1], residuals[1:]
    lag1 = (float(np.corrcoef(left, right)[0, 1])
            if np.std(left) > 0 and np.std(right) > 0 else None)
    dw = float(np.sum(np.diff(residuals) ** 2) / sse)
    centered = residuals - mean
    denominator = centered @ centered
    acf = [float(centered[lag:] @ centered[:-lag] / denominator) for lag in range(1, lags + 1)]
    q = float(n * (n + 2) * sum(r * r / (n - lag) for lag, r in enumerate(acf, 1)))
    # Exploratory portmanteau screen; fitting a trend and small n affect calibration.
    q_p = float(stats.chi2.sf(q, lags))
    leverage = np.sum((design @ np.linalg.inv(design.T @ design)) * design, axis=1)
    mse = sse / (n - 2)
    standardized = residuals / np.sqrt(mse * (1 - leverage))
    cooks = standardized ** 2 * leverage / (2 * (1 - leverage))
    return ResidualDiagnostics(
        lag1, dw, lags, q, q_p, q_p < 0.05, mean, std, rmse, maximum,
        tuple(float(v) for v in standardized), tuple(float(v) for v in cooks),
        tuple(int(y) for y in years[np.abs(standardized) > 2]),
        tuple(int(y) for y in years[cooks > 4 / n]),
    )


def analyze_annual_trend(annual: pd.DataFrame, *, hac_lags: int | None = None) -> TrendResult:
    """Fit Celsius against calendar year; require >=3 finite, consecutive years.

    Accepts the complete-year output of annual_trend_ready. No sorting,
    deletion, imputation, or outlier removal occurs. Gaps are rejected because
    HAC lags must represent consecutive calendar years. Constant responses
    have undefined R²; numerically exact fits have unavailable inference and
    autocorrelation diagnostics because residual variance is effectively zero.
    """
    if not {"year", "temperature_c"}.issubset(annual.columns):
        raise ValueError("Annual data requires year and temperature_c columns.")
    if len(annual) < 3:
        raise ValueError("At least three annual observations are required.")
    if "is_complete" in annual and not annual["is_complete"].eq(True).all():
        raise ValueError("Use complete years only (annual_trend_ready) for trend analysis.")
    try:
        years = annual["year"].to_numpy(dtype=float)
        temperatures = annual["temperature_c"].to_numpy(dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError("Years and temperatures must be numeric and finite.") from exc
    if not np.isfinite(years).all() or not np.isfinite(temperatures).all():
        raise ValueError("Years and temperatures must be finite; missing values are not dropped.")
    if not np.equal(years, np.floor(years)).all() or not np.equal(np.diff(years), 1).all():
        raise ValueError("Years must be unique, ordered, consecutive calendar years for HAC.")
    n = len(years)
    lags = select_hac_lags(n) if hac_lags is None else hac_lags
    if isinstance(lags, bool) or not isinstance(lags, Integral) or not 0 <= lags < n:
        raise ValueError(f"HAC lags must be an integer between 0 and {n - 1}.")
    # Center the design for numerical stability; report intercept at calendar year 0.
    x = years - years.mean()
    design = np.column_stack((np.ones(n), x))
    centered_y = temperatures - temperatures.mean()
    slope = float(x @ centered_y / (x @ x))
    intercept = float(temperatures.mean() - slope * years.mean())
    fitted = temperatures.mean() + slope * x
    residuals = temperatures - fitted
    sse = float(residuals @ residuals)
    sst = float(centered_y @ centered_y)
    constant = bool(np.all(temperatures == temperatures[0]))
    degenerate = bool(np.max(np.abs(residuals)) <= 100 * np.finfo(float).eps * max(1, np.max(np.abs(temperatures))))
    warnings = [
        "OLS confidence intervals and p-values are conditional on a linear mean, independent, homoskedastic errors and an adequate error-distribution approximation.",
        "HAC intervals and p-values are approximate: short annual series provide limited information about dependence; bandwidth choice matters.",
        "Statistical significance does not establish causation or practical importance; interpret magnitude and uncertainty in context.",
        "Residual and outlier screens are exploratory; absence of a flag does not establish independence, normality, or constant variance.",
    ]
    if degenerate:
        ols = hac = SlopeInference(0.0, None, None, None)
        warnings.append("Residual variance is effectively zero: confidence intervals, p-values and residual dependence diagnostics are unavailable.")
    else:
        ols = _inference(slope, float(np.sqrt(sse / (n - 2) / (x @ x))), n - 2)
        covariance = newey_west_covariance(design, residuals, lags)
        hac = _inference(slope, float(np.sqrt(max(0.0, covariance[1, 1]))), n - 2)
    diagnostics = _diagnostics(years, residuals, design, degenerate)
    if diagnostics.autocorrelation_detected:
        warnings.append("Residual autocorrelation detected by an exploratory Ljung–Box screen: naive OLS confidence intervals and p-values may be unreliable.")
    if diagnostics.potential_outlier_years or diagnostics.influential_years:
        warnings.append("Potential outlier or influential years were flagged for review; all observations were retained.")
    return TrendResult(
        tuple(int(y) for y in years), tuple(float(t) for t in temperatures), slope,
        intercept, None if constant else float(1 - sse / sst),
        float(temperatures[-1] - temperatures[0]), tuple(float(v) for v in fitted),
        tuple(float(v) for v in residuals), ols, hac, int(lags), diagnostics, tuple(warnings),
    )
