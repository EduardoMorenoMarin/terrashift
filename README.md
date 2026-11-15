# TerraShift

TerraShift makes historical temperature change across South America easier to
explore and interpret. It turns NASA MERRA-2 country-average temperature series
into interactive charts, a regional trend map, and statistical summaries with
explicit uncertainty and data provenance.

The project is being prepared for participation in the **NASA Space Apps
Challenge 2026**. Its focus is transparent exploration of historical climate
data, with reproducible methods and clear scientific limits.

## Features

- Explore monthly temperatures and complete annual averages for 12 countries,
  with selectable year ranges, diagnostics, and processed CSV downloads.
- Estimate annual linear trends in °C per decade with ordinary least squares
  (OLS) and Newey–West (HAC) adjusted 95% confidence intervals.
- Compare temperature histories and individual trend estimates for 2–5 countries.
- View country-level trends on an interactive South America map using bundled
  Natural Earth boundaries.
- Switch between English and Spanish while retaining the analysis selections.
- Inspect methodology and sources within the dashboard. Explanatory text is
  generated from deterministic statistical rules.
- Use a separate descriptive Climate Fingerprint pipeline to study anomalies
  against country-specific 2000–2019 baselines. This analysis is not integrated
  into the dashboard; derived tables are in `reports/climate_fingerprint/`.

## Data source and coverage

Climate data come from NASA's **Modern-Era Retrospective analysis for Research
and Applications, Version 2 (MERRA-2)**, produced by the Global Modeling and
Assimilation Office (GMAO) at NASA Goddard Space Flight Center and distributed
through NASA GES DISC's Giovanni service. The project uses collection
**M2TMNXSLV v5.12.4**, variable **T2M** (2-meter air temperature), as monthly
area-averaged country series. MERRA-2 is a reanalysis combining observations
with a physical model, rather than a collection of individual thermometer readings.

- **Geography:** Argentina, Bolivia, Brazil, Chile, Colombia, Ecuador, Guyana,
  Paraguay, Peru, Suriname, Uruguay, and Venezuela.
- **Monthly coverage:** January 2000–September 2026, 321 observations per country,
  as recorded in the audited country registry and inventory.
- **Complete annual coverage:** 2000–2025, 26 years. The nine available months of
  2026 are retained as monthly data and excluded from annual charts and trends.
- **Requested versus available dates:** exports requested data through October
  2026, but contain no October observation. Filenames and request dates must not
  be used as substitutes for observed coverage.

See the [collection documentation](https://doi.org/10.5067/AP1B0BA5PD2K),
[NASA MERRA-2 overview](https://gmao.gsfc.nasa.gov/gmao-products/merra-2/), and
[NASA Giovanni](https://giovanni.gsfc.nasa.gov/giovanni/).
The map uses Natural Earth v5.1.2 public-domain display boundaries; full
[boundary attribution and limitations](data/geography/README.md) are included.

## Technology

Python, Streamlit, Plotly, pandas, NumPy, and SciPy power the application and
analysis. pytest supports automated checks. Dependency ranges are declared in
[requirements.txt](requirements.txt). No database or separate backend service
is required.

## Installation and local execution

From the repository root, create an environment using Python 3.11 or later
(Python 3.12 is a suggested starting point):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

**Provide the source data before launching:** the current country CSV files are
ignored by Git and are not included in a fresh clone. Place the reviewed exports
in `data/raw/` using the exact filenames and bytes recorded in
[metadata/country_mapping.json](metadata/country_mapping.json). This includes
the Peru file with a historical-looking filename; the registry, rather than the
filename date, identifies its active release. The loader verifies checksums and
Giovanni shape references. A newly downloaded export may differ from the recorded
release and must not be treated as byte-identical reproduction.

```bash
.venv/bin/python -m streamlit run app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`.
On Windows, substitute `.venv\Scripts\python` for `.venv/bin/python`.
The current development environment uses Python 3.14; other Python versions
have not been independently verified for this submission cleanup.

## Processing and reproducibility

The loader separates Giovanni metadata from observations and validates timestamps,
numeric values, ordering, duplicates, and missing calendar months. Cleaning
converts Kelvin to Celsius (`°C = K − 273.15`) without changing source files.
Annual averages weight each month equally and require 12 valid months for trend
analysis. Missing values are not interpolated, and flagged outliers are not removed.
Trend inference requires at least three complete consecutive years.

OLS estimates the slope; HAC adjusts its uncertainty for serial dependence and
unequal error variance. The dashboard includes residual diagnostics and explains
how to interpret individual confidence intervals and p-values.

Reproducibility records include:

- `metadata/country_mapping.json`: country associations, ISO-3 codes, source
  filenames, SHA-256 checksums, Giovanni shape references, and coverage.
- `metadata/region_inventory.json` and `metadata/dataset_provenance.json`: audited
  source details and release history; earlier metadata are in `metadata/history/`.
- `reports/climate_fingerprint/manifest.json`: descriptive-analysis settings,
  source checksums, and derived-file checksums.
- `scripts/validate_data.py`, `scripts/validate_regions.py`, and
  `scripts/analyze_trends.py`: source validation and historical trend analysis.
  These require the corresponding raw data. `scripts/analyze_fingerprint.py`
  regenerates descriptive outputs and writes a report; it is not needed to run
  the dashboard.

For a lightweight check that does not load climate data:

```bash
.venv/bin/python -m pytest -q tests/test_app_imports.py tests/test_i18n.py::test_catalog_parity_nonempty_values_and_all_templates_interpolate tests/test_i18n.py::test_static_translation_references_exist_and_ui_copy_is_not_embedded
```

The full test suite includes tests requiring local NASA CSV files.

## Known limitations and experimental work

Country averages hide local variation and extremes. Country identities follow
recorded manual Giovanni selections; exports do not independently name countries
or include their polygon coordinates. Generalized map boundaries differ from
Giovanni extraction boundaries and do not verify the spatial averaging.

Short records and selected time windows can produce sensitive trend estimates;
HAC uncertainty is approximate. Individual p-values are not adjusted for multiple
comparisons. Different significance labels or overlapping intervals do not test
whether two countries' trends differ. Historical associations do not establish
causation or predict future conditions.

Climate Fingerprint uses a 20-year reference, not a standard 30-year climate
normal. Its summaries weight countries equally and are not area-weighted South
American climate estimates.

Probabilistic machine-learning forecasting was investigated experimentally.
**The Phase 5H.3 final test is complete and did not meet its predefined acceptance
criteria.** Experimental forecasts are not validated predictions and are not a
dashboard feature. The final-test metrics and locked evaluation protocol are not
present in this checkout, so no numerical ML performance claims are made here.
