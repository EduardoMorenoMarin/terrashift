"""Generate reproducible Climate Fingerprint datasets and a descriptive report."""

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.climate_fingerprint import (
    ZERO_TOLERANCE_C, FingerprintDataset, build_fingerprint, country_peak_anomalies,
    largest_positive_anomalies, load_fingerprint, most_shared_years, partial_year_anomalies,
    shared_warm_years, similar_country_patterns, widespread_warm_years,
)


def sensitivity_fingerprint(fingerprint: FingerprintDataset) -> FingerprintDataset:
    """Historical 2000–2009 sensitivity, using the exact same loaded observations."""
    monthly = {country: rows[['date', 'temperature_k']].copy()
               for country, rows in fingerprint.monthly.groupby('country')}
    registry = {row.country: {'iso3': row.iso3} for row in fingerprint.annual_references.itertuples()}
    return build_fingerprint(monthly, registry, replace(fingerprint.config, reference_end=2009))


def _csv(table: pd.DataFrame, path: Path, *, index: bool = False) -> None:
    serialized = table.copy()
    for column in serialized.columns:
        if pd.api.types.is_object_dtype(serialized[column].dtype):
            serialized[column] = serialized[column].map(
                lambda value: json.dumps(list(value), separators=(',', ':')) if isinstance(value, (tuple, list)) else value)
    serialized.to_csv(path, index=index, date_format='%Y-%m-%d', lineterminator='\n')


def report_text(fingerprint: FingerprintDataset, summary: pd.DataFrame, partial: pd.DataFrame,
                similarities: pd.DataFrame, sensitivity: pd.DataFrame) -> str:
    cfg = fingerprint.config
    codes = dict(zip(fingerprint.annual_references.iso3, fingerprint.annual_references.country))
    ranked = summary.loc[summary.fully_observed].sort_values(
        ['n_above_threshold', 'mean_country_anomaly_c', 'year'], ascending=[False, False, True]).head(6)
    positive = most_shared_years(summary, 'n_positive')
    threshold = most_shared_years(summary, 'n_above_threshold')
    widespread = widespread_warm_years(summary)
    events = largest_positive_anomalies(fingerprint)
    peaks = country_peak_anomalies(fingerprint)
    partial_valid = partial.loc[partial.is_complete_selection]
    text = f'''# South America's Climate Fingerprint — Phase 5G.1

## Definition and methods

Source: the 12 registered NASA MERRA-2 / Giovanni T2M country-average series,
January 2000–September 2026. Source validation and geographic provenance are
unchanged. This is analysis only; the Streamlit UI and OLS/HAC methods are untouched.

Primary reference: **{cfg.reference_start}–{cfg.reference_end}** ({cfg.reference_end-cfg.reference_start+1} complete years per country).
An annual anomaly is a complete-year arithmetic mean of 12 monthly temperatures
minus that country's reference-period mean annual temperature. Monthly anomalies
subtract the matching calendar month's reference mean, using 20 observations per
month. Reference data never extend beyond the declared historical interval.
These are departures from each country's own baseline, not comparisons of absolute
country climates and not estimates of relative warming rates.

Warm threshold: each country's **{cfg.warm_quantile*100:g}th percentile** of reference annual temperatures,
equivalently reference annual anomalies. NumPy's explicit `method="linear"` uses
linear interpolation at zero-based sorted rank `(n−1)q`. Exceedance is strictly
above this threshold; equality is not counted. Absolute differences at or below
{ZERO_TOLERANCE_C:g} °C are numerical zero only, preventing floating-point artifacts.
The 20-year sample gives coarse, estimator-sensitive tail information. The cutoff
is descriptive, not an absolute climate-risk, local-heatwave or weather-event label.
This chosen 20-year reference is not a 30-year standard climate normal.

The year summary gives positive, negative, zero and threshold-exceedance counts
with contributing ISO-3 lists. Its mean weights each country **1/12**, equally,
not by area, population or the number of valid cells. It is not South America's
area-average anomaly. Incomplete country panels have an unavailable regional mean
and are excluded from shared-year discovery rankings. Missing anomalies never
become zero. An incomplete reference raises an explicit error rather than silently
shortening the baseline.

“Widespread warm” means at least **{int(summary.widespread_required.iloc[0])} of {int(summary.n_countries.iloc[0])} countries**
exceeding their own cutoff (at least {cfg.widespread_fraction*100:g}%). This prespecified descriptive rule is
not a hypothesis test. Countries are spatially dependent and are never treated as
independent trials; no binomial probabilities, regional p-values or uncertainty
from an independent-country assumption are calculated.

## Observed findings, complete years {cfg.first_year}–{cfg.last_year}

All {len(fingerprint.annual)} country/year cells are present; {int(fingerprint.annual.is_complete.sum())} are complete.
The country-by-year anomaly matrix has {fingerprint.anomaly_matrix.shape[0]} rows × {fingerprint.anomaly_matrix.shape[1]} years.

| Year | Positive / 12 | Negative / 12 | Above own warm cutoff / 12 | Equal-country mean anomaly (°C) |
| --- | ---: | ---: | ---: | ---: |
'''
    for row in ranked.itertuples():
        text += f'| {row.year} | {row.n_positive} | {row.n_negative} | {row.n_above_threshold} | {row.mean_country_anomaly_c:+.6f} |\n'
    text += ('\nYears tied for the largest positive count: **' + ', '.join(str(y) for y in positive.year)
             + f'** ({int(positive.n_positive.iloc[0])}/12 each).\n'
             + 'Years tied for the largest cutoff count: **' + ', '.join(str(y) for y in threshold.year)
             + f'** ({int(threshold.n_above_threshold.iloc[0])}/12 each).\n'
             + 'The widespread rule selects **' + ', '.join(str(y) for y in widespread.year.sort_values()) + '**.\n')
    text += '\nContributors to the leading shared-year results:\n\n'
    for row in ranked.head(4).itertuples():
        text += (f'- **{row.year}** above cutoff: ' + ', '.join(row.above_threshold_countries)
                 + '. Positive: ' + ', '.join(row.positive_countries)
                 + '. Negative: ' + (', '.join(row.negative_countries) or 'none') + '.\n')
    text += '''
### Largest positive country/year departures in this record

These rank anomalies relative to each country's own mean, not absolute
warmth, warming rate, statistical significance or local extremes.

| Country | Year | Annual anomaly (°C) |
| --- | ---: | ---: |
'''
    for row in events.itertuples():
        text += f'| {row.country} | {row.year} | {row.annual_anomaly_c:+.6f} |\n'
    text += '\nCountry-specific peak years, including every exact tie:\n\n'
    for row in peaks.sort_values('iso3').itertuples():
        text += f'- {row.country}: {row.year}, {row.annual_anomaly_c:+.6f} °C.\n'
    text += '''
These differences show that countries need not share a peak year. A country's
larger anomaly can also reflect its variability; no direct statistical test of
between-country differences is implied. “Peak” applies only to the selected
2000–2025 record, never to all history.

### Similar annual anomaly patterns

Pearson correlations use the same full 26 annual observations per pair. They
are descriptive: shared long-term trends can increase level correlation. The
first-difference correlation separately describes paired year-to-year changes;
it does not establish independence or causation. Missing windows and constant
patterns return an explicit unavailable status rather than pairwise deletion or
spurious perfect similarity. Selection among 66 pairs is exploratory.

| Country pair | Anomaly-level r | Year-to-year-change r |
| --- | ---: | ---: |
'''
    for row in similarities.loc[similarities.status.eq('ok')].head(3).itertuples():
        change = f'{row.change_correlation:.6f}' if np.isfinite(row.change_correlation) else 'Unavailable'
        text += f'| {codes[row.iso3_a]} / {codes[row.iso3_b]} | {row.correlation:.6f} | {change} |\n'
    text += f'''
## Separate January–September 2026 comparison

There are {len(fingerprint.monthly.loc[fingerprint.monthly.year.eq(2026)])} monthly anomaly values in 2026 (9 × 12 countries).
**2026 is absent from the complete-year annual fingerprint.** Its nine-month
comparison subtracts the mean of January–September reference months, equivalently
the mean of 20 historical January–September averages. It is never compared with
a full-year baseline, ranked alongside full years or assessed with the annual
90th-percentile cutoff.

{int(partial_valid.partial_anomaly_c.gt(0).sum())}/{len(partial)} countries have positive same-month partial anomalies.
The equal-country mean of these matched partial anomalies is
**{partial_valid.partial_anomaly_c.mean():+.6f} °C**, across {len(partial_valid)} fully observed country selections.
This is not a 2026 annual estimate or forecast.

| Country | January–September 2026 anomaly (°C) |
| --- | ---: |
'''
    for row in partial.sort_values('iso3').itertuples():
        text += f'| {row.country} | {row.partial_anomaly_c:+.6f} |\n'
    text += '''
## Baseline sensitivity — interpretation depends on the reference

An illustrative **2000–2009** reference repeats the same calculations on the same
observations, using 10 reference years. It is a sensitivity check, not a preferred
replacement baseline; its percentile is even less stable. The primary published
fingerprint remains 2000–2019. Country-specific offsets change anomaly magnitudes
and signs, and the shorter distributions change thresholds and selected years.

| Year | Primary positives | Alternative positives | Primary above cutoff | Alternative above cutoff | Primary mean (°C) | Alternative mean (°C) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
'''
    chosen = sorted(set(ranked.head(4).year))
    for year in chosen:
        primary = summary.loc[summary.year.eq(year)].iloc[0]
        alternate = sensitivity.loc[sensitivity.year.eq(year)].iloc[0]
        text += (f'| {year} | {primary.n_positive} | {alternate.n_positive} | {primary.n_above_threshold} | '
                 f'{alternate.n_above_threshold} | {primary.mean_country_anomaly_c:+.6f} | {alternate.mean_country_anomaly_c:+.6f} |\n')
    alternate_widespread = widespread_warm_years(sensitivity).year.sort_values().tolist()
    text += '\nAlternative widespread years: **' + ', '.join(map(str, alternate_widespread)) + '**.\n'
    text += '''
Constant baseline shifts do not change within-pair Pearson correlations, but they
do change anomaly labels. Reference years are used to estimate their own baseline
and percentile: their counts are descriptive, not held-out forecast validation.
No post-2019 observations enter the primary reference or thresholds.

## Scientific limits and interpretation

The observed concentration of warm departures is consistent with shared patterns
in these country-average series; it does not identify their causes. Do not infer
local heatwaves, daily extremes, climate impacts or unprecedented conditions
outside 2000–2025. The countries are unequal in area and are spatially dependent;
the equal-country summary is a chosen aggregation, not a continental area mean.
The short and potentially nonstationary reference, year-to-year dependence,
reanalysis/model uncertainties, manual Giovanni selections and unavailable spatial
averaging details all limit interpretation. No independent uncertainty estimates
for the source observations are provided here. Threshold counts do not measure
risk or prove significant differences. Existing NASA, Giovanni and Natural Earth
attribution and geographic limitations remain in the project documentation.

## Reuse, reproducibility and future visualization

Run `.venv/bin/python scripts/analyze_fingerprint.py` from the project root.
The script can also be invoked from another working directory. Use
`--output-directory` and `--report` to select artifact destinations.

`annual_fingerprint.csv` is the metadata-rich long country/year dataset;
`annual_anomaly_matrix.csv` is its numeric ISO-3 × year view. Annual and calendar-
month baseline tables make the references and thresholds auditable.
`monthly_anomalies.csv` retains monthly observations, including 2026.
`shared_warm_years.csv` retains ISO-3 contributors for every count and regional
mean. Other outputs include country peaks, positive-anomaly rankings, all 66
pairwise similarities, separate partial-2026 results and baseline sensitivity.
List fields in CSVs use JSON arrays, and `manifest.json` records source checksums,
configuration, scientific policies and artifact checksums. Results are generated
from data; no temperatures or discovery numbers are hardcoded in the engine/report.

Recommended next-phase views (not implemented in Streamlit):

1. A country × year anomaly heatmap, with a shared diverging Celsius scale centered
   on zero, baseline in the title and incomplete data gray. Add symbols for each
   country's own threshold rather than replacing the continuous scale.
2. A yearly count chart (positive and above threshold) with contributor tooltips,
   paired with the explicitly equal-country mean series. Label the denominator 12.
3. Country small multiples on anomaly axes, retaining individual threshold lines;
   show 2026 monthly anomalies in a separate seasonal or month × country panel.
4. A separate same-month partial-year panel, never appended as a full annual column.
5. Correlation and first-difference correlation matrices with their common year
   window and warnings about shared trends; do not label correlations as causes.

Implementation references: [NumPy quantiles](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html)
and [NumPy Pearson correlation](https://numpy.org/doc/stable/reference/generated/numpy.corrcoef.html).
These document calculations, not additional climate data sources.
'''
    return text


def write_analysis(fingerprint: FingerprintDataset, output_directory: Path, report: Path) -> dict:
    raw = (ROOT / 'data/raw').resolve()
    if output_directory.resolve().is_relative_to(raw) or report.resolve().is_relative_to(raw):
        raise ValueError('Analysis output must not be written into raw source data.')
    summary = shared_warm_years(fingerprint)
    if not summary.fully_observed.any():
        raise ValueError('Shared-discovery reporting requires at least one fully observed target year.')
    partial = partial_year_anomalies(fingerprint)
    similarities = similar_country_patterns(fingerprint)
    alternative = sensitivity_fingerprint(fingerprint)
    sensitivity = shared_warm_years(alternative)
    output_directory.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    tables = {
        'annual_fingerprint.csv': fingerprint.annual,
        'monthly_anomalies.csv': fingerprint.monthly,
        'annual_references.csv': fingerprint.annual_references,
        'monthly_references.csv': fingerprint.monthly_references,
        'shared_warm_years.csv': summary,
        'country_peak_anomalies.csv': country_peak_anomalies(fingerprint),
        'largest_positive_anomalies.csv': largest_positive_anomalies(fingerprint),
        'similar_country_patterns.csv': similarities,
        'partial_2026_january_september.csv': partial,
        'sensitivity_2000_2009_shared_years.csv': sensitivity,
        'sensitivity_2000_2009_references.csv': alternative.annual_references,
    }
    for filename, table in tables.items():
        _csv(table, output_directory / filename)
    matrix = output_directory / 'annual_anomaly_matrix.csv'
    _csv(fingerprint.anomaly_matrix, matrix, index=True)
    report.write_text(report_text(fingerprint, summary, partial, similarities, sensitivity), encoding='utf-8')
    files = sorted([*tables, matrix.name])
    manifest = {
        'analysis': 'TerraShift Phase 5G.1; descriptive analysis only',
        'config': asdict(fingerprint.config), 'quantile_method': 'linear',
        'zero_tolerance_c': ZERO_TOLERANCE_C,
        'sources': fingerprint.sources.to_dict('records'),
        'annual_cells': len(fingerprint.annual), 'monthly_cells': len(fingerprint.monthly),
        'reference_policy': 'Require every complete reference year and all calendar-month observations; no imputation.',
        'weighting': 'Each country 1/12; no independent-country inference, area or population weighting.',
        'missing_target_policy': 'Retain unavailable annual cells; regional mean/discoveries require complete panels.',
        'partial_policy': '2026 monthly retained; Jan–Sep compared only with reference Jan–Sep; no annual threshold.',
        'similarity_policy': 'Full-window Pearson levels and first differences; constant/incomplete pairs unavailable; no p-values.',
        'sensitivity_reference': asdict(alternative.config),
        'artifact_sha256': {name: hashlib.sha256((output_directory / name).read_bytes()).hexdigest() for name in files},
        'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(),
    }
    (output_directory / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, default=ROOT / 'reports/climate_fingerprint')
    parser.add_argument('--report', type=Path, default=ROOT / 'docs/phase_5g_1_climate_fingerprint.md')
    args = parser.parse_args()
    try:
        fingerprint = load_fingerprint()
        manifest = write_analysis(fingerprint, args.output_directory, args.report)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Fingerprint analysis failed: {exc}\n')
    print(f"Annual fingerprint: {manifest['annual_cells']} cells; monthly anomalies: {manifest['monthly_cells']}.")
    print(shared_warm_years(fingerprint)[['year', 'n_positive', 'n_above_threshold', 'mean_country_anomaly_c']].to_string(index=False))
    print(f'Report: {args.report}')
    print(f'Derived data and source manifest: {args.output_directory}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
