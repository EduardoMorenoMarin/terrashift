# Phase 5B.1 public copy audit

Scope: Streamlit text, dynamic summaries, charts, table labels, tooltips,
empty states, errors and optional technical material. Raw datasets, the country
registry, validation logic and statistical calculations are unchanged.

| Surface | Before | After / placement |
| --- | --- | --- |
| Introduction | “A changing climate. A clearer signal.” | “Explore South America's changing temperatures” with the measured variable, region and period in the introduction. |
| Country provenance | “Peru (user-confirmed selection)” beside results; `user_confirmed` in a table | Results show the country and period. Methodology explains individual country boundary selections through NASA Giovanni. The source table shows Country and Data source. |
| Geographic details | Repeated country-verification caveats and empty bounding boxes | Methodology explains extraction-time selections and traceability. Original boundary identifiers appear only in Technical details. Internal status and verification fields stay in metadata. |
| Result labels | “HAC-adjusted p-value,” “Annual observations used,” “First-to-last annual difference” | “Trend p-value,” “Years analyzed,” “First-to-last change,” with concise help text. |
| Data tables | `temperature_c`, `valid_months`, `is_complete` | “Temperature (°C),” “Months available,” “Complete year” (Yes/No). Download fields are unchanged. |
| Dynamic Explore interpretation | A long paragraph combining trend, residual checks, provenance and cautions | Short paragraphs for estimated change, confidence interval and endpoint change. Residual checks are in Data & diagnostics; source and causal qualifications are in Methodology. |
| Dynamic Compare interpretation | Repeated technical caveats and a long list of statistical restrictions | Short country groups for estimated warming/cooling, evidence, and uncertainty; separate-country testing explained in plain English. |
| Chart language | “OLS trend · annual means,” “HAC 95% CI,” `ns`, `n/a` | “Linear trend,” “95% confidence interval,” “Not significant,” “Not assessed.” Hover details retain precise values and full statistical significance labels. |
| Comparison qualifications | “No direct tests of between-country slope differences are performed…” | “Trends are estimated separately for each country. Differences between countries should be interpreted cautiously…” followed by the precise distinction from rate-difference testing. |
| Errors | Exceptions exposing registry paths, checksums and internal statuses | Actionable public messages; detailed exceptions remain in application logs. |
| Navigation and captions | Repeated method descriptions beside charts | Results and short chart captions in Explore/Compare; source, methods and interpretation guidance in Methodology; formulas in Technical details. |
| Attribution | Multiple agency acronyms and repeated qualifiers | NASA Space Apps Challenge project branding and NASA MERRA-2 data attribution; full source links remain in Methodology. |

## Scientific content retained

- Celsius units, annual aggregation requirements, slopes per decade, actual
  confidence bounds, p-values, R² and sample size remain visible.
- Methodology defines MERRA-2 reanalysis and distinguishes regional estimates
  from individual thermometer readings and local extremes.
- Statistical evidence remains conditional on analysis assumptions; confidence
  intervals that include zero are described as uncertain rather than no change.
- Nearly exact fits and short records retain unavailable-inference messages.
- HAC adjustment, dependence, small-sample uncertainty, OLS assumptions, lag
  selection, diagnostic rules and unadjusted multiple testing are retained in
  the relevant explanations or optional technical material.
- Separate-country significance is distinguished from differences between
  countries. Temperature levels are distinguished from rates of change.
- Results describe change, not its cause; country averages hide local variation.
- Boundary selections are described as project extraction choices. Nothing
  asserts independent verification of country labels or official NASA ownership.

## Verification

Automated public-copy checks inspect all tab content, including collapsed
expanders, table values and columns, widget help and Plotly chart specifications.
Checks cover annual/monthly views, multiple countries and periods, short records,
positive/negative/constant/uncertain trends, and sanitized error messages.
The full suite passed with 145 tests. All three data validation/analysis scripts
passed; file fingerprints confirm that data, provenance, validation and
statistical computation files are unchanged.

Visual browser QA remains unverified in this environment; Streamlit AppTest
executes the application and its interactions, but does not assess appearance.
