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
Phase 5A adds an inventory of 12 Giovanni exports confirmed by the user to cover
all sovereign South American countries. Each file has the same collection,
variable, monthly coverage and observation count. The original Peru bytes are
now named with a `_PER.csv` suffix. The user explicitly confirms selecting each
country individually in Giovanni and manually naming the files with the
corresponding country suffixes. All 12 associations are `user_confirmed`,
preserving the distinction from independent geographic verification.

Implemented features include metadata-aware loading, strict input validation,
Kelvin-to-Celsius conversion, monthly tables, annual means and completeness
flags, data provenance, OLS linear trends, HAC-adjusted uncertainty estimates,
residual diagnostics, and automated tests. The interactive Streamlit dashboard
adds Plotly annual/monthly charts, selectable year ranges, annual trend toggling,
dynamic statistical summaries, scientific interpretation, methodology and CSV
downloads. Raw observations remain unchanged.

Development progress: Phase 1 (exploration) and Phase 2 (loading and cleaning)
are implemented. Phase 3 (statistical trend analysis) is implemented and
validated. Phase 4 (interactive dashboard) is implemented and tested through
Streamlit's application runtime. Phase 5A adds the multi-country data pipeline,
read-only inventory and explicit provenance mapping. The dashboard now resolves
each selected country through the country registry, validating the file checksum
and Giovanni shape, without depending on historical filenames. Phase 5B adds
interactive country selection, temperature comparisons and individual warming-rate
comparisons. Phase 5B.1 refines public copy, table labels and scientific
explanations without changing data or calculations. Phase 5C adds an interactive
South America trend map with bundled, attributed Natural Earth boundaries,
explicit ISO-3 joins, shared year controls and a synchronized country selector.
Phase 5D adds American English and Latin American Spanish throughout the dashboard,
including scientific interpretations, charts, maps, tables and messages.
No deployment, machine learning, chatbot, or
AI-generated explanations are implemented. Interpretation uses deterministic
text based on the computed statistics. Further phases await approval.

## Installation and usage

Use Python **3.11 or 3.12** for a new installation (3.12 recommended for future
Community Cloud deployment). From the project root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`.
Use Streamlit **1.55 or later** (as specified in `requirements.txt`) for stable
widget identity and tracked tabs when translated labels change.
On Windows, use `.venv\Scripts\python` in place of `.venv/bin/python`.
The code uses Python 3.11-compatible syntax. The current development environment
was tested on Python 3.14; a separate 3.11/3.12 runtime check remains advisable
before deployment.

To run all checks:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/validate_data.py
.venv/bin/python scripts/analyze_trends.py
.venv/bin/python scripts/validate_regions.py
```

The single-dataset validation and analysis scripts accept an explicit CSV path;
without one they locate the original Peru bytes by the preserved provenance
checksum, allowing the `_PER.csv` rename. Generic `load_data()` automatic
discovery still requires exactly one CSV and now raises an ambiguity error;
use an explicit path or country loader for multi-file directories.
The dashboard defaults to Peru and calls `load_country(selected_country)` using
`metadata/country_mapping.json`, relative to `app.py`; it does not depend
on the shell's working directory. The original unsuffixed demonstration name
is allowed by `.gitignore`, but the newly suffixed CSV names remain ignored by
the existing policy. A future deployment must explicitly include the required
reviewed files in version control. No module writes to
the original CSV. Provenance is stored separately in that metadata file.

## Exploring the dashboard

The dashboard uses three tabs:

- **Explore:** select one of the 12 registered countries for detailed annual
  inference, diagnostics, temperature visualization and processed-data download.
  The default is Peru; select a different country in the sidebar. The map above
  the details shows annual temperature trends in °C/decade across all 12 countries,
  with a diverging scale centered on zero, country/period hover details and a dark
  outline around the selected country. Drag to pan and use the map zoom controls.
- **Compare:** select **2–5 distinct countries** in the sidebar. Interactive
  temperature lines show annual or monthly values. Horizontal warming-rate bars
  show the annual OLS slope with individual HAC-adjusted 95% intervals and
  significance indicators. A statistical table reports the actual analysis
  period, complete annual observation count, slope per decade, HAC interval and
  p-value, R² and individual significance. No comparison is shown until at least
  two countries are selected.
- **Methodology:** NASA attribution, preparation and inference methods,
  geographic provenance and scientific limitations.

Shared start/end years and frequency apply to Explore and Compare. Each country
uses the same color across charts and selection order. The Explore trend toggle
does not add trend lines to monthly or comparison temperature charts. Short
periods retain temperature data while unavailable slopes and significance are
marked explicitly; countries lacking estimable slopes are omitted from the
rate bars and retained in the comparison table.

The map always uses annual trend estimates, including when temperature charts
show monthly values. Colors describe country-level averages, not within-country
spatial variation or statistical significance. Gray means unavailable rather
than zero. The availability table retains every country and explains missing
estimates. Hover and table labels distinguish the selected period from the
actual fitted years when incomplete endpoint years are excluded. Short records
show a caution; fewer than three complete consecutive years cannot yield a trend.

`core/map_data.py` loads each country through the existing validated loader and
calls `prepare_period`; it introduces no statistical calculation. Geographic
validation requires all 12 registry entries to match exactly one polygon feature
by ISO-3. The explicit `iso3` field is independent of legacy filename suffixes.
`core/map_charts.py` renders a Plotly `Choroplethmap` with a symmetric color range
and a white background, requiring no tile service, token, or runtime boundary
download. The boundary subset is only 22 KB. Source, version, public-domain terms,
checksums and extraction details are in [the geography attribution](data/geography/README.md).
Display boundaries are generalized and differ from the original Giovanni
extraction boundaries; they do not redefine the NASA country averages.

Country clicks do not change Explore. Streamlit exposes selection events rather
than a general Plotly click callback. Reliable polygon selection has not been
verified across the supported versions, so the existing **Country to explore** selector controls both the map
outline and Explore details. This uses no additional dependency. See the
[implementation and interaction notes](docs/phase_5c_map.md).

Country options and file resolution come from the registry, without separate
country-to-file lists. Tests exercise the actual repository data and a temporary
fixture with a renamed registry file. Registry, checksum and file errors are
displayed gracefully. All country selections are user-confirmed rather than
independently verified by the exports.

Choose start and end years in the sidebar. Every change filters the monthly
data and recomputes complete annual means and inference using the existing
`core/` pipeline. Short selections keep their temperature records visible;
trend inference requires at least three complete consecutive years. Reversed
ranges show a message rather than stale statistics.

Annual view supports showing or hiding the annual OLS fit. Monthly view retains
seasonal variation and disables the trend overlay; it does not fit a monthly
regression. The statistical summary always describes complete annual means for
the selected period. “Data & diagnostics” includes readable data tables,
diagnostic details and a CSV download matching the selected frequency and
years. Annual downloads retain their original valid-month counts and
completeness fields. Methodology contains NASA links and a simplified source
table; original boundary references and formulas are in “Technical details.”

`app.py` contains the Streamlit interface; `core/dashboard_data.py` handles
period selection, exports and deterministic interpretation;
`core/dashboard_charts.py` creates Plotly figures. Neither helper duplicates
aggregation or statistical calculations.

`core/country_comparison.py` validates selections, loads countries through the
registry, and prepares each selected period using `prepare_period` and the
existing annual inference module. It provides the comparison table, consistent
country colors and deterministic interpretation; no new statistical estimators
or pairwise tests are introduced.

## English and Spanish

At the top of the sidebar, choose **English** or **Español** in the
**Language / Idioma** selector. English is the default for a new browser session.
The change immediately updates Explore / Explorar, Compare / Comparar and
Methodology / Metodología, including map text, chart axes and hover labels,
country names (for example, Peru → Perú and Brazil → Brasil), metric help,
diagnostics, scientific interpretations, warnings, errors, sources and footer.
Language is scoped to the current session; a page reload/new session returns
to English rather than persisting a browser-wide preference.

Switching preserves the country and comparison selections, start/end years,
annual/monthly view, trend toggle and selected tab. Registry names and ISO-3
identifiers remain internal. Language-only reruns reuse the session's scientific
outputs without reloading NASA data or recomputing trends. Changed analysis
inputs or source-file metadata trigger fresh work. Other reruns keep the existing
refresh behavior; cached failures are not reused. Numerical values and decimal
notation remain unchanged in both languages.

The lightweight translation architecture uses:

- `locales/en.json` and `locales/es.json`: matching stable keys and complete
  sentence templates, including the full methodology text.
- `core/i18n.py`: explicit `t(key, lang="en", **variables)`, country and month
  labels, count forms, and strict catalog/placeholder validation. No process-wide
  language variable or translation dependency is used.
- `core/dashboard_copy.py`: translated copies of public tables and notices,
  plus Plotly locale configuration; source frames are never modified.
- `core/dashboard_state.py`: per-session analysis reuse, source metadata checks
  and selected-tab preservation.

To add or modify a translation:

1. Add the same descriptive key to both UTF-8 JSON catalogs, or edit its existing
   values without changing the key. Keep URLs, identifiers and proper names intact.
2. Use named interpolation placeholders with identical names, conversions and
   format specifications in both languages. For example,
   `"{slope:+.3f} °C per decade"` / `"{slope:+.3f} °C por década"`.
   For literal braces, including Plotly `%{...}` fields, double the braces in
   the catalog: `%{{x:.3f}}`.
3. Render with `t("key.name", lang, slope=value)`. Put full sentences in the
   catalogs; select scientific branches using keys rather than language checks.
   For counts, add `.one` and `.other` keys and use
   `plural("count.key", count, lang)`. Country names use `country_name`.
4. Restart the Streamlit process after editing JSON catalogs (they are cached
   after strict startup validation), and run `.venv/bin/python -m pytest -q`.
   Missing keys, duplicate keys, differing key sets, blank values, incompatible
   placeholders or incorrect interpolation arguments fail explicitly.

Monthly hover text and tick labels use catalog month names directly. Common
Plotly toolbar labels also receive a local dictionary, with no external locale
download. Streamlit-owned browser chrome, such as dataframe toolbar/search,
fullscreen controls and application menus, may retain framework wording: the
app does not replace those controls with custom components. Browser-native UI
and linked external websites retain their own language. Those framework-owned
strings and browser-level interaction/rendering still require manual review.

Processed CSV downloads intentionally preserve the existing machine-readable
schema, canonical country fields, dates, numeric values and filenames in both
languages. Raw NASA datasets, country provenance, geographic assets, statistical
methods and validation-script output are unchanged. See the
[Phase 5D implementation notes](docs/phase_5d_localization.md).

Absolute temperature levels reflect geography, elevation and climate and are
not warming rates. Individual significance against zero does not establish a
significant difference between countries; one significant and one
non-significant slope are not evidence of such a difference. Individual
confidence intervals are not a substitute for a direct between-country test.
The displayed p-values are unadjusted for multiple testing. Point estimates
alone do not establish a definitive fastest-warming country. HAC inference is
approximate, short-window results can be sensitive, country averages hide local
variation, and neither comparisons nor small p-values establish causation.

## Future Community Cloud deployment

Deployment has not been performed. When deployment is explicitly authorized:

1. Include `app.py`, `core/`, `locales/`, `requirements.txt`, `.streamlit/config.toml`,
   `metadata/country_mapping.json`, `metadata/dataset_provenance.json`, and the
   `data/geography/` and required CSVs named in the country registry in the GitHub repository. The
   newly suffixed raw files still need to be explicitly allowed by `.gitignore`
   and included in a future authorized commit.
2. Connect that repository and branch in Streamlit Community Cloud and set
   the main file path to `app.py`.
3. Select Python 3.12 in Advanced settings. Community Cloud installs packages
   from the root `requirements.txt`; no separate backend, database or system
   packages are required by this application.
4. Verify startup, the data file, controls, downloads and reference statistics
   on the deployed app. No custom domain is configured.

See [Streamlit's deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app).
Keep `.streamlit/secrets.toml`, `.env*`, local environments and caches out of
version control. Only the theme configuration is intended for tracking.

```python
from core.data_loader import load_data, resolve_original_source
from core.data_cleaning import (
    clean_monthly, annual_mean_temperatures, annual_trend_ready,
)

loaded = load_data(resolve_original_source())
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

No files of cleaned observations are automatically written. Peru has
user-confirmed selection provenance: the CSV shape identifier alone does not verify the
country name.

## Multi-country data architecture (Phase 5A)

`metadata/country_mapping.json` is a versioned country registry for Argentina,
Bolivia, Brazil, Chile, Colombia, Ecuador, Guyana, Paraguay, Peru, Suriname,
Uruguay and Venezuela. Entries bind a country to an exact filename, SHA-256,
Giovanni shape identifier, provenance status and evidence. These are explicit
records, never mappings inferred at runtime from file order, temperatures or
global filename bounds.

All 12 mappings are **`user_confirmed`**. The user explicitly confirms personally
downloading each country individually from Giovanni and manually assigning the
filename country labels. These intentional labels provide selection provenance;
the pipeline does not infer country identity from file order or temperature.
The exact suffixes are retained as assigned:

| Country | Filename suffix |
| --- | --- |
| Argentina | ARG |
| Bolivia | BOL |
| Brazil | BR |
| Chile | CH |
| Colombia | COL |
| Ecuador | ECU |
| Guyana | GUY |
| Paraguay | PAR |
| Peru | PER |
| Suriname | SURI |
| Uruguay | URU |
| Venezuela | VEN |

The prior mapping status and evidence remain in each entry's
`provenance_history`. Peru also matches its historical source checksum.
Reserve `independently_verified` for a mapping backed by an authoritative
country-to-shape reference. No country identity is independently verified by
the CSVs themselves. Existing `metadata/dataset_provenance.json` is preserved
unchanged, including its historical original filename.

`core/region_data.py` exposes `load_country(country)` and returns source NASA
metadata, mapping evidence, checksum and standardized tables:

| Table | Columns |
| --- | --- |
| Monthly | country, date, temperature_k, temperature_c |
| Annual | country, year, temperature_k, temperature_c, valid_months, is_complete |
| Complete annual | same annual columns, restricted to complete years |

```python
from core.region_data import load_country

peru = load_country("Peru")
print(peru.metadata)           # NASA metadata preserved separately
print(peru.provenance)         # explicit mapping and evidence
print(peru.monthly.head())
print(peru.complete_annual.head())
```

Pending country mappings cannot be loaded as countries. Confirmed entries are
checked against file bytes and the reproduction URL shape. Duplicate countries,
files, hashes and shapes are rejected, as are duplicate JSON keys and unsafe
filenames. Every dataset must identify `M2TMNXSLV_5_12_4_T2M` in its Giovanni
URL, monthly resolution, and the full January 2000–December 2025 calendar
coverage, consistent with metadata and reproduction URL dates. Kelvin units
come from the existing NASA documentation verification for that exact variable;
the real exports do not explicitly state units. Contradictory explicit unit
metadata is rejected.

The loader delegates strict record validation to `core/data_loader.py` and
all conversion/aggregation to `core/data_cleaning.py`. Missing calendar months,
duplicates, invalid/nonfinite numbers and conflicting coverage raise informative
errors. Blank and declared fill temperatures remain missing; affected years
are flagged and excluded from complete annual output, while monthly records
are retained. No imputation, interpolation or outlier removal occurs.

`core/dataset_audit.py` performs a separate raw-field inspection so defects can
be counted even for files the strict loader rejects. It uses the shared
pipeline for processed values and annual summaries. `scripts/validate_regions.py`
audits **all** CSVs, including unmapped files, and prints country candidates,
source filenames, counts, coverage, missing months, complete years, temperature
ranges and separate data/provenance status. Exit codes: **0** for valid data and
resolved mappings, **1** for invalid data/mapping/file errors, **2** for unresolved
country mappings with otherwise valid data. Current validation exits **0**:
all 12 datasets are valid and all 12 mappings are user-confirmed.

`metadata/region_inventory.json` is the read-only inspection snapshot generated
during the initial Phase 5A audit, before explicit country confirmation. Its
country summary is historical and retains that earlier pending state; the
registry and live validator provide current provenance status. The snapshot
records every file's SHA-256, raw header, metadata records,
reproduction URL, collection/version/variable, shape, actual date range, quality
counts, unit evidence and temperature range. To create a new snapshot without
overwriting existing metadata:

```bash
.venv/bin/python scripts/validate_regions.py --report /tmp/terrashift_inventory.json
```

Current inspection: **12/12 valid files**, each with **312 monthly records** and
**26 complete years**. No missing months, duplicate timestamps, malformed
records, invalid numeric values, fill occurrences, blanks or nonfinite
temperatures were found. All share collection/version/variable and documented
Kelvin units. All bounding boxes are empty and each URL has a distinct shape
identifier; no shape-to-country name table is included. **All 12 mappings are
user-confirmed, with no unresolved entries**. There is exactly one dataset per
country, with distinct filenames, checksums and shapes, and no extra raw CSVs.
Numerical validity and user confirmation do not constitute independent
geographic verification.

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
describe within-country variation or daily extremes. No machine learning or
AI-generated explanations are implemented.

## Validation status

Phase 2 tests are available in `tests/test_data.py`. Phase 3 synthetic and NASA
pipeline tests are in `tests/test_trend_analysis.py`. Dashboard helper and
Streamlit interaction tests are in `tests/test_dashboard.py`. Validation
completed with **232 tests passing**, and all three scripts—`scripts/validate_data.py`,
`scripts/analyze_trends.py`, and `scripts/validate_regions.py`—executed successfully. The raw CSV SHA-256 still
matches the provenance record. Tests include full-period reference statistics,
period filtering and recalculation, short and invalid ranges, incomplete years,
CSV exports, chart semantics, interpretation and Streamlit runtime interactions.
Phase 5A tests in `tests/test_regions.py` add synthetic multi-country fixtures,
mapping conflicts, missing files, collection/variable/units/coverage failures,
missing and invalid values, country labels, pipeline reuse and audit behavior.
Phase 5B tests in `tests/test_country_comparison.py` cover registry-driven options,
stable colors, 2–5-country selection, invalid inputs, period filtering,
annual/monthly values, missing-value preservation, slope and confidence-whisker
presentation, statistical tables, short periods, interpretation and Streamlit
country/comparison interactions.
Phase 5B.1 tests in `tests/test_public_copy.py` check public wording across all
tabs, tables, chart specifications, help text and collapsed expanders, including
multiple countries, date ranges, unavailable estimates and error states.
Internal provenance status values stay in metadata and never appear in the
rendered interface. Public labels are separate from the unchanged CSV schema.
Phase 5C tests in `tests/test_map.py` cover all 12 ISO-3 mappings and geographic
joins, real and synthetic map values, date filtering, missing and insufficient
data, Plotly construction and map/Explore synchronization. Browser interactions
remain a manual review item; see [the Phase 5C notes](docs/phase_5c_map.md).
Phase 5D adds 59 tests in `tests/test_i18n.py` for the translation contract,
country names, singular/plural forms, chart/map/table localization, unchanged
scientific values, bilingual interpretations and errors, session isolation,
selected-tab preservation, and language changes without data reload or inference.
`tests/test_app_imports.py` also imports the real application in a fresh Python
process with an isolated bytecode cache, verifying chart module paths, imported
function identities and call signatures. Unresolved application imports fail
this check rather than being hidden by pytest's existing module cache.
`scripts/validate_regions.py` reports 12 valid files, no unresolved countries,
no country load errors, and returns exit code 0. Raw files and the original provenance
are unchanged. The original Peru scripts still reproduce the previous trend.

The Streamlit AppTest executed the app and controls against the real registry
without import or runtime errors. Additional tests verify registry-based filename
resolution after a rename in a temporary fixture, graceful registry load errors,
and user-confirmed provenance for all 12 countries. Streamlit AppTest also
executes all three tabs and changing country/comparison controls. During Phase 5B,
a separate live-server launch
was blocked by this environment's socket
permissions (`PermissionError: Operation not permitted`), so HTTP/browser
rendering was not verified here. This is an environment verification limit;
local startup and a Python 3.11/3.12 environment should be checked before a
future deployment. No commit, push or deployment has been performed.

Dependencies use bounded compatibility ranges; the exact resolved versions
should be captured after a successful installation for a frozen environment.
