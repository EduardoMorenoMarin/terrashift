# TerraShift AI

TerraShift AI is a NASA Space Apps Challenge project for investigating historical
changes in Earth's environmental variables using real NASA data. Its scientific
objective is to quantify environmental trends and assess their statistical
uncertainty while preserving reproducible data provenance.

The current dataset is NASA MERRA-2, collection M2TMNXSLV v5.12.4, variable T2M
(2-meter air temperature), exported through Giovanni. It contains 312 monthly
area-averaged observations from January 2000 through December 2025. Peru was
selected manually by the user; the export records shape
`state_dept_countries_2017/shp_174` but does not independently identify its country.
Original temperatures are in Kelvin, verified against NASA documentation.

Implemented features include metadata-aware loading, strict input validation,
Kelvin-to-Celsius conversion, monthly tables, annual means and completeness
flags, data provenance, OLS linear trends, HAC-adjusted uncertainty estimates,
residual diagnostics, and automated tests. Raw observations remain unchanged.

Development progress: Phase 1 (exploration) and Phase 2 (loading and cleaning)
are implemented. Phase 3 (statistical trend analysis) is implemented and
validated. Phase 4 has not started.
No dashboard, machine learning, or AI explanations are implemented.

## Installation and usage

Requires Python 3.11 or newer. From the project root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_data.py
.venv/bin/python scripts/analyze_trends.py
```

The validation script also accepts an explicit CSV path. Automatic discovery
requires exactly one CSV in `data/raw/`. Raw data is ignored by Git and is never
written by these modules. Provenance is stored separately in
`metadata/dataset_provenance.json`.

```python
from core.data_loader import load_data
from core.data_cleaning import (
    clean_monthly, annual_mean_temperatures, annual_trend_ready,
)

loaded = load_data()
monthly = clean_monthly(loaded.observations)
annual = annual_mean_temperatures(monthly)
complete_annual = annual_trend_ready(annual)
print(loaded.metadata)
print(loaded.missing_months)
```

The loader reads the actual table header rather than assuming a fixed number
of metadata lines. It preserves metadata separately, validates field counts,
parses timestamps and temperatures strictly, rejects duplicates and unordered
records, and reports missing calendar months without inserting observations.
Requested date metadata, when present, also defines endpoint gap checks.
Blank temperatures and the declared fill value become missing values; invalid
numeric tokens and nonfinite literals raise errors. Temperatures below absolute
zero raise errors; no statistical outlier filtering is performed.

Cleaning copies the validated monthly data and adds Celsius. Annual summaries
use equally weighted arithmetic means of available monthly values, not
day-weighted means. Each year has a valid-month count and `is_complete` flag.
Years with fewer than 12 valid months retain their partial mean but are excluded
by `annual_trend_ready`. Entirely absent years between observed endpoints appear
with zero valid months. Missing requested endpoint months remain visible in
`loaded.missing_months`; annual summaries cover observed calendar years.

No files of cleaned observations are automatically written. Peru is
user-reported provenance: the CSV shape identifier alone does not verify the
country name.

## Statistical analysis

`core/trend_analysis.py` fits annual mean Celsius against calendar year using
ordinary least squares (OLS), including an intercept. Outputs include slopes
per year and decade, an intercept at calendar year zero (not a meaningful
physical extrapolation), R², two-sided slope p-values, 95% confidence intervals,
and significance flags at alpha=0.05. First-to-last observed change is reported
separately from the regression slope.

Only complete years enter analysis. At least three finite, ordered,
consecutive annual observations are required. No values are silently dropped.
Gaps are rejected so a HAC lag always represents a calendar-year interval.
Constant series have undefined R². Fits with effectively zero residual variance
report unavailable intervals, p-values and residual dependence diagnostics
rather than claiming statistical significance from a degenerate fit.

Both inference methods use the same slope. Classical OLS standard errors assume
independent, homoskedastic errors; Student-t inference additionally depends on
an adequate error-distribution approximation. The second method uses a
Bartlett/Newey–West sandwich covariance with finite-sample correction n/(n-2).
Its automatic lag rule is `floor(4*(n/100)^(2/9))`, capped at n-1: **two lags for
26 annual observations**. This follows the convention documented by
[statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html),
implemented directly with NumPy without adding statsmodels as a dependency.
Both intervals use Student-t critical values with n-2 degrees of freedom;
the HAC reference distribution remains an approximation, not an exact
small-sample guarantee. SciPy supplies distribution functions, following the
[OLS interval convention](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.linregress.html).

For bandwidth sensitivity, run `python scripts/analyze_trends.py --hac-lags 1`
(or another nonnegative integer less than the sample size). Lag zero only
adjusts for heteroskedasticity. HAC changes uncertainty rather than the fitted
trend; intervals may widen or narrow. HAC does not fully resolve uncertainty
from short records, long-range dependence, changing climate variability,
nonlinearity, spatial aggregation, or data provenance limitations.

Diagnostics include lag-1 residual Pearson correlation, Durbin–Watson,
residual mean/SD/RMSE and maximum absolute residual, and an exploratory
Ljung–Box screen over up to three lags (min(3,n-2)), using a chi-square reference
with that many degrees of freedom. This screen's calibration is approximate
after fitting a trend and with small samples. A p-value below 0.05 triggers a
warning about naive OLS inference. A non-significant screen does not establish
independence. No normality or constant-variance claim is inferred from it.
Internally standardized residuals above 2 in absolute value and Cook's distance
above 4/n flag potential outliers or influential years for review. These
heuristics do not justify removing observations; all data is retained.

Statistical significance is conditional on the model and does not prove
causation. Practical importance requires assessing the trend magnitude and
uncertainty in environmental context. Regional reanalysis averages do not
describe within-country variation or daily extremes. No dashboard, machine
learning or AI explanations are implemented.

## Validation status

Phase 2 tests are available in `tests/test_data.py`. Phase 3 synthetic and NASA
pipeline tests are in `tests/test_trend_analysis.py`. Validation completed with
**58 tests passing**, and both `scripts/validate_data.py` and
`scripts/analyze_trends.py` executed successfully. The raw CSV SHA-256 still
matches the provenance record. The run used Python 3.14, pandas 3.1.1,
NumPy 2.5.4, SciPy 1.18.1 and pytest 9.2.0; Python 3.11 was not separately tested.

Dependencies use bounded compatibility ranges; the exact resolved versions
should be captured after a successful installation for a frozen environment.
