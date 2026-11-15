# South America's Climate Fingerprint — Phase 5G.1

## Definition and methods

Source: the 12 registered NASA MERRA-2 / Giovanni T2M country-average series,
January 2000–September 2026. Source validation and geographic provenance are
unchanged. This is analysis only; the Streamlit UI and OLS/HAC methods are untouched.

Primary reference: **2000–2019** (20 complete years per country).
An annual anomaly is a complete-year arithmetic mean of 12 monthly temperatures
minus that country's reference-period mean annual temperature. Monthly anomalies
subtract the matching calendar month's reference mean, using 20 observations per
month. Reference data never extend beyond the declared historical interval.
These are departures from each country's own baseline, not comparisons of absolute
country climates and not estimates of relative warming rates.

Warm threshold: each country's **90th percentile** of reference annual temperatures,
equivalently reference annual anomalies. NumPy's explicit `method="linear"` uses
linear interpolation at zero-based sorted rank `(n−1)q`. Exceedance is strictly
above this threshold; equality is not counted. Absolute differences at or below
1e-12 °C are numerical zero only, preventing floating-point artifacts.
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

“Widespread warm” means at least **9 of 12 countries**
exceeding their own cutoff (at least 75%). This prespecified descriptive rule is
not a hypothesis test. Countries are spatially dependent and are never treated as
independent trials; no binomial probabilities, regional p-values or uncertainty
from an independent-country assumption are calculated.

## Observed findings, complete years 2000–2025

All 312 country/year cells are present; 312 are complete.
The country-by-year anomaly matrix has 12 rows × 26 years.

| Year | Positive / 12 | Negative / 12 | Above own warm cutoff / 12 | Equal-country mean anomaly (°C) |
| --- | ---: | ---: | ---: | ---: |
| 2024 | 12 | 0 | 12 | +1.342896 |
| 2023 | 12 | 0 | 12 | +1.098481 |
| 2020 | 12 | 0 | 9 | +0.648908 |
| 2025 | 11 | 1 | 7 | +0.490622 |
| 2015 | 11 | 1 | 5 | +0.404733 |
| 2019 | 11 | 1 | 4 | +0.448193 |

Years tied for the largest positive count: **2020, 2023, 2024** (12/12 each).
Years tied for the largest cutoff count: **2023, 2024** (12/12 each).
The widespread rule selects **2020, 2023, 2024**.

Contributors to the leading shared-year results:

- **2024** above cutoff: ARG, BOL, BRA, CHL, COL, ECU, GUY, PER, PRY, SUR, URY, VEN. Positive: ARG, BOL, BRA, CHL, COL, ECU, GUY, PER, PRY, SUR, URY, VEN. Negative: none.
- **2023** above cutoff: ARG, BOL, BRA, CHL, COL, ECU, GUY, PER, PRY, SUR, URY, VEN. Positive: ARG, BOL, BRA, CHL, COL, ECU, GUY, PER, PRY, SUR, URY, VEN. Negative: none.
- **2020** above cutoff: ARG, BOL, CHL, COL, GUY, PER, PRY, SUR, VEN. Positive: ARG, BOL, BRA, CHL, COL, ECU, GUY, PER, PRY, SUR, URY, VEN. Negative: none.
- **2025** above cutoff: ARG, BRA, CHL, GUY, SUR, URY, VEN. Positive: ARG, BOL, BRA, CHL, COL, GUY, PER, PRY, SUR, URY, VEN. Negative: ECU.

### Largest positive country/year departures in this record

These rank anomalies relative to each country's own mean, not absolute
warmth, warming rate, statistical significance or local extremes.

| Country | Year | Annual anomaly (°C) |
| --- | ---: | ---: |
| Guyana | 2024 | +2.362710 |
| Suriname | 2024 | +1.961306 |
| Venezuela | 2024 | +1.949885 |
| Uruguay | 2023 | +1.874428 |
| Brazil | 2024 | +1.694576 |

Country-specific peak years, including every exact tie:

- Argentina: 2023, +1.045867 °C.
- Bolivia: 2024, +1.524078 °C.
- Brazil: 2024, +1.694576 °C.
- Chile: 2016, +0.596031 °C.
- Colombia: 2024, +1.017668 °C.
- Ecuador: 2024, +0.726920 °C.
- Guyana: 2024, +2.362710 °C.
- Peru: 2024, +1.511808 °C.
- Paraguay: 2024, +1.554824 °C.
- Suriname: 2024, +1.961306 °C.
- Uruguay: 2023, +1.874428 °C.
- Venezuela: 2024, +1.949885 °C.

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
| Peru / Venezuela | 0.915467 | 0.869043 |
| Guyana / Suriname | 0.894228 | 0.852144 |
| Colombia / Venezuela | 0.893753 | 0.936896 |

## Separate January–September 2026 comparison

There are 108 monthly anomaly values in 2026 (9 × 12 countries).
**2026 is absent from the complete-year annual fingerprint.** Its nine-month
comparison subtracts the mean of January–September reference months, equivalently
the mean of 20 historical January–September averages. It is never compared with
a full-year baseline, ranked alongside full years or assessed with the annual
90th-percentile cutoff.

12/12 countries have positive same-month partial anomalies.
The equal-country mean of these matched partial anomalies is
**+0.781804 °C**, across 12 fully observed country selections.
This is not a 2026 annual estimate or forecast.

| Country | January–September 2026 anomaly (°C) |
| --- | ---: |
| Argentina | +0.101930 |
| Bolivia | +0.715645 |
| Brazil | +1.275002 |
| Chile | +0.418249 |
| Colombia | +0.544434 |
| Ecuador | +0.981900 |
| Guyana | +1.247931 |
| Peru | +0.861397 |
| Paraguay | +0.870874 |
| Suriname | +1.161990 |
| Uruguay | +0.226404 |
| Venezuela | +0.975886 |

## Baseline sensitivity — interpretation depends on the reference

An illustrative **2000–2009** reference repeats the same calculations on the same
observations, using 10 reference years. It is a sensitivity check, not a preferred
replacement baseline; its percentile is even less stable. The primary published
fingerprint remains 2000–2019. Country-specific offsets change anomaly magnitudes
and signs, and the shorter distributions change thresholds and selected years.

| Year | Primary positives | Alternative positives | Primary above cutoff | Alternative above cutoff | Primary mean (°C) | Alternative mean (°C) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2020 | 12 | 12 | 9 | 10 | +0.648908 | +0.735584 |
| 2023 | 12 | 12 | 12 | 12 | +1.098481 | +1.185157 |
| 2024 | 12 | 12 | 12 | 12 | +1.342896 | +1.429572 |
| 2025 | 11 | 11 | 7 | 9 | +0.490622 | +0.577298 |

Alternative widespread years: **2020, 2023, 2024, 2025**.

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
