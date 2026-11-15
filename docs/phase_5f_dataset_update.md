# Phase 5F — NASA dataset update audit and implementation

The active source is NASA MERRA-2 via Giovanni, collection **M2TMNXSLV v5.12.4**,
variable **T2M (2-meter air temperature)**. All 12 files were inspected before
code changes. The existing loaders, conversion, aggregation and OLS/HAC analysis
were reused. No raw file was renamed or modified, and no missing observation was
fabricated, annualized or interpolated.

## Root cause and observed discrepancies

The first reproduced failure was `load_country("Peru")` raising a source-not-found
error: the registry referenced the previous `_PER.csv` filename, which is absent.
The observed replacement is named
`g4.areaAvgTimeSeries.M2TMNXSLV_5_12_4_T2M.20000101-20251231.180W_90S_180E_90N_SURI_PER.csv`.
Eleven other filenames now include `20261031` instead of `20251231`, so their
previous registry paths are also absent. The filenames did not all remain the
same as the previous release.

Further failures would remain after changing paths alone:

1. All 12 replacement byte checksums differ from their registered predecessors.
2. `region_data.validate_dataset()` previously enforced the January 2000–December
   2025 calendar, including the requested metadata and URL dates.
3. The validation scripts resolved the original historical Peru checksum. Those
   original bytes are no longer present, so the resolver finds zero matches.
4. Both locale catalogs contained fixed 2000–2025 public coverage descriptions.
5. Annual chart builders could plot a partial-year arithmetic mean as an annual
   observation. The existing trend pipeline already required complete years and
   was scientifically correct; its calculation method did not need changing.

The CSV schema itself is unchanged: eight lines before the `time`/T2M header,
monthly timestamps and the same area-mean temperature column. There are no
malformed observations or duplicate/missing months inside actual coverage.

**Every source requests through October 31, 2026 in both its metadata and
reproduction URL, but ends at September 1, 2026 in the observation table.** The
requested October observation is absent from every export. That discrepancy is
explicitly reviewed and recorded rather than silently treated as a full request.
Its cause cannot be established from the export. No assumption about NASA release
latency is made.

The Peru filename also has a stale 2025 date label and misleading `SURI_PER`
suffix. Its source reproduction URL has the exact previously registered Peru
shape `state_dept_countries_2017/shp_174`. All 12 original shape references match
exactly and one-to-one. Existing country associations, ISO-3 keys, user confirmation,
evidence and limitations remain unchanged. Matching the same shape does not
constitute new independent verification of the country name.

## Actual per-country coverage

| Country | ISO-3 | First observation | Last observation | Months | Complete years | Incomplete 2026 |
| --- | --- | --- | --- | ---: | --- | ---: |
| Argentina | ARG | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Bolivia | BOL | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Brazil | BRA | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Chile | CHL | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Colombia | COL | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Ecuador | ECU | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Guyana | GUY | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Paraguay | PRY | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Peru | PER | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Suriname | SUR | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Uruguay | URY | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |
| Venezuela | VEN | 2000-01-01 | 2026-09-01 | 321 | 2000–2025 (26) | 9 months |

All 3,852 monthly records are valid finite numeric values. Across all files:

- Zero missing months inside January 2000–September 2026; one explicitly recorded
  requested-but-unavailable month per file: October 2026.
- Zero duplicate timestamps or duplicate calendar months.
- Zero malformed records, invalid dates, invalid numeric tokens, nonfinite values,
  blanks or occurrences of the declared fill value (`1000000000000000`).
- Exactly 26 complete calendar years (2000–2025), plus nine months in incomplete 2026.
- All share the required Giovanni host, area-average service, collection, version,
  variable and monthly resolution. No geography/shape conflicts or unmapped files.
- Units are **Kelvin**, based on the retained NASA T2M documentation evidence.
  The exports do **not** contain an explicit unit field; this is documented, not
  represented as direct CSV unit verification. Contradictory explicit unit fields
  and collection/version/variable declarations are rejected.

Full metadata, raw headers, reproduction URLs, quality counters, temperature
ranges, complete/incomplete-year lists and the requested/observed discrepancy are
recorded in `metadata/region_inventory.json`.

### Updated SHA-256 checksums

These identify the provided bytes, not newly generated datasets.

| Country | SHA-256 |
| --- | --- |
| Argentina | `7ab5263c78af1b71b32853efa5f691a27add1c035f7a1ef5271a2ffc215bbb20` |
| Bolivia | `a227ebbdc50f48c0d5bac9d27792034e68e70677a6a7f9ece74105942b160e24` |
| Brazil | `21cf144dfc3ef84de04993ed9324d2fb8c7254d2970e6b84c901416bf0d905ba` |
| Chile | `07edcea6bc64db8ff1230dff377ba61bbf7aaeb5a02d2e726261837b3fbd2c62` |
| Colombia | `f02143a3dc0958036d1edd8357b4dd8b6d8e1e19aa7cf29e275993ac46f504ec` |
| Ecuador | `52ba21ac6cfcb4dbcc0a2a707aaa775a87ba47f8d6dfdef9bc1673d06bde2dd5` |
| Guyana | `9b0d61d217e5098e3506145b59237b2f4ccf1222676bce401a8e114603bea154` |
| Paraguay | `68d6fb1d1cc187f705034aa68bc2083884a113bad1b6d497e9b068eedb965bdc` |
| Peru | `80625d4c6879618b17770f7f78170c21d3d0da96b9f044ca378fa704fe4fa79a` |
| Suriname | `35a8517522b7c9236e4b8610ebb901fbc3b351c3487bb025b27b1fb9b72896ca` |
| Uruguay | `e059966e03c74d8a645e0c235160b0ff6c362aea7b1f6ea47905d1e45564d6d9` |
| Venezuela | `89c1f940e4a4977736801c36cf2f950ccd655d04439e95306fbc36eda0967507` |

## Registry and provenance changes

`metadata/country_mapping.json` now records the actual observed filenames and
checksums. Each entry has a reviewed `coverage` manifest with actual start/end
months and count, original requested timestamps, explicitly listed unavailable
requested months and the audit explanation. Complete and incomplete year metadata
are recorded separately. Previous filename/checksum/shape/status records remain
in `dataset_history`.

`metadata/dataset_provenance.json` preserves its original historical fields and
adds `current_dataset` for the active Peru export. The original top-level
requested dates and observations describe the old release, as the added historical
fields note explains. The new section has actual coverage, source details, active
checksum, shape, complete years and partial-year counts.

Unmodified pre-update copies of all three metadata files are archived under
`metadata/history/phase_5d/`. The prior inventory's historical pending statuses
are preserved there; the regenerated current inventory records current mappings.
Historical raw CSV bytes were not available and were not reconstructed.

## Validation architecture and future updates

`validate_dataset(loaded, coverage=...)` checks actual dates and count against the
reviewed manifest, compares the requested URL and metadata timestamps with each
other and the manifest, and rejects collection, variable, version, unit, cadence,
calendar-gap or unreviewed-shortage conflicts. An explicit manifest must enumerate
its exact terminal request shortage and provide a review note. Internal gaps
cannot be declared away. With no manifest, every requested month must be present.
There is no hardcoded terminal year or observation count in this validator.
A synthetic future 2027 extension verifies that later periods work without code
changes when their metadata are consistent.

`inspect_dataset(path, coverage=entry["coverage"])` separates missing observed
months from `missing_requested_months`, counts duplicate calendar months as well
as timestamps, and records all complete/incomplete years. Direct inspection
without the reviewed manifest correctly rejects the October shortage as unreviewed.
The regional validation script supplies each mapped manifest, flags inconsistent
coverage across countries and treats unmapped extra files as errors.

`load_data()` retains the raw requested interval and therefore still reports
October in `loaded.missing_months`. `load_country()` exposes missing months inside
reviewed observation coverage separately from `unavailable_requested_months`.
The latter is explained in localized Methodology and audit/CLI output.

The new `resolve_reference_source()` uses the validated active Peru registry.
`resolve_original_source()` retains its strict historical meaning and does not
silently return new bytes. Both validation scripts use the active reference by
default and validate explicit sources against their metadata, using a reviewed
manifest only when their checksum matches a registered release.

For a future extension, inspect all source bytes and metadata, review discrepancies,
archive prior metadata, update exact filenames/checksums and manifest values, and
regenerate the inventory. A raw replacement alone remains intentionally insufficient
to bypass the established integrity checks.

## Partial-year scientific handling and dashboard behavior

Monthly views and downloads include all 321 observations through September 2026.
Year controls include 2026. Sidebar, coverage captions and Methodology derive their
monthly and complete-year date labels from loaded data. English and Spanish
messages explain the requested October/available September distinction and the
actual annual fit period.

The unchanged aggregation computes equal-weight monthly arithmetic summaries
and flags completeness at 12 valid monthly values. The 2026 row remains an
explicitly incomplete nine-month summary for audit/data tables and CSV exports;
it is not annualized. Annual chart helpers mask its temperature values and retain
gaps, so partial-year means do not appear as annual points. Source tables remain
unchanged by this presentation operation.

`annual_trend_ready()` and the existing regression continue to use only complete
years. For a 2000–2026 selection, Explore metrics, comparison rates and map colors
use 2000–2025. Map hover/table labels distinguish selected and fitted periods.
Comparisons with zero complete years report unavailable analysis periods.
Selecting 2026 alone retains nine monthly observations and provides no annual
trend or valid annual point. No October–December observations are inferred.

The Peru reference slope remains **+0.370206 °C/decade**, HAC 95% interval
**[0.132071, 0.608341]**, p-value **0.00376199**. All 12 extended-window fits exactly
match fits using the same provided observations restricted to complete 2000–2025.
The statistical methodology, Kelvin conversion and geographic boundaries are
unchanged. Language switching still preserves country/period/view/tab state and
reuses scientific outputs on language-only reruns.

## Files created and modified

Created:

- `tests/test_dataset_update.py` — 33 Phase 5F audit/scientific/UI tests.
- `docs/phase_5f_dataset_update.md` — this report.
- `metadata/history/phase_5d/country_mapping.json`.
- `metadata/history/phase_5d/dataset_provenance.json`.
- `metadata/history/phase_5d/region_inventory.json`.

Modified:

- `app.py` — dynamic coverage, fit-period and partial-year explanations.
- `core/region_data.py` — reviewed coverage and strict source validation.
- `core/data_loader.py` — active-reference resolver; existing CSV parsing unchanged.
- `core/dataset_audit.py` — requested/available coverage and full year audit.
- `core/dashboard_data.py` — annual chart presentation helper.
- `core/dashboard_charts.py` — mask partial values in annual charts.
- `core/dashboard_copy.py` — localized dynamic coverage labels and notices.
- `core/country_comparison.py` — actual complete-year periods for unavailable fits.
- `core/map_data.py` — localized partial-year exclusion notice.
- `locales/en.json`, `locales/es.json` — dynamic coverage and scientific messages.
- `metadata/country_mapping.json`, `metadata/dataset_provenance.json`,
  `metadata/region_inventory.json` — active release and historical traceability.
- `scripts/validate_data.py`, `scripts/analyze_trends.py`,
  `scripts/validate_regions.py` — active source and explicit coverage reporting.
- `tests/test_data.py`, `tests/test_dashboard.py`, `tests/test_regions.py`,
  `tests/test_trend_analysis.py`, `tests/test_i18n.py` — legitimately changed
  coverage/reference expectations and explicit short-period selections. Original
  historical-period scientific reference assertions are retained.
- `README.md` — current coverage, methodology, manifests and reference usage.

## Verification and remaining limitations

The full suite passes: **265 tests in 62.81 seconds**, comprising the 232 prior
tests with legitimate coverage expectation updates plus 33 new Phase 5F tests.
`git diff --check` passes. The three validation scripts all return exit code 0. The regional audit reports
12/12 valid files, zero unresolved mappings and zero country load errors.
The 33 new tests independently passed before the combined suite. They cover each
country's manifest and raw integrity, requested/observed coverage, metadata
conflicts, annual completeness, future extension, monthly filtering, comparisons,
map calculations and English/Spanish 2026 navigation and language switching.

Streamlit AppTest executes the real dashboard and controls, including all tabs.
Browser testing is unavailable in this environment: no supported browser tool,
Chromium/Chrome/Firefox executable or Playwright installation was found. Native
browser map/zoom and narrow-screen rendering therefore remain manual review items.

The missing requested October month, unusual Peru filename, indirect source-unit
evidence and unavailable old raw bytes are documented source limitations, not
silently repaired. The application is restored using the actual September cutoff.
No unreviewed source conflict remains. There was no commit, push or deployment;
Phase 5F stops for user review.
