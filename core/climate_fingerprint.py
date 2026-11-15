"""Descriptive country temperature anomalies; no UI, trend changes or inference.

Country means are equally weighted across valid months, following the existing
cleaning pipeline. References must contain every complete calendar year. No
reference estimate uses observations outside its declared historical interval.
"""

from dataclasses import dataclass
from itertools import combinations
from numbers import Integral, Real
from pathlib import Path
import re

import numpy as np
import pandas as pd

from core.data_cleaning import annual_mean_temperatures, annual_trend_ready, clean_monthly
from core.region_data import COUNTRIES, MAPPING_PATH, RAW_DIRECTORY, load_country, read_country_mapping

ZERO_TOLERANCE_C = 1e-12  # Floating-point zero only, not a substantive warming cutoff.


@dataclass(frozen=True)
class FingerprintConfig:
    reference_start: int = 2000
    reference_end: int = 2019
    first_year: int = 2000
    last_year: int = 2025
    warm_quantile: float = .90
    widespread_fraction: float = .75

    def __post_init__(self):
        for value in (self.reference_start, self.reference_end, self.first_year, self.last_year):
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise ValueError('Reference and analysis years must be integers.')
        if self.reference_start >= self.reference_end or self.first_year > self.last_year:
            raise ValueError('Require at least two reference years and an ordered analysis interval.')
        for value in (self.warm_quantile, self.widespread_fraction):
            if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value) or not 0 < value < 1:
                raise ValueError('Quantile and widespread fraction must be strictly between zero and one.')

    @property
    def reference_definition(self) -> str:
        return f'{self.reference_start}–{self.reference_end}; complete calendar years; equal-month means'


@dataclass
class CountryAnomalies:
    annual: pd.DataFrame
    monthly: pd.DataFrame
    annual_reference: dict
    monthly_references: pd.DataFrame


@dataclass
class FingerprintDataset:
    annual: pd.DataFrame
    monthly: pd.DataFrame
    annual_references: pd.DataFrame
    monthly_references: pd.DataFrame
    config: FingerprintConfig
    sources: pd.DataFrame

    @property
    def anomaly_matrix(self) -> pd.DataFrame:
        """ISO-3 × year values; metadata/completeness are in the long annual table."""
        return self.annual.pivot(index='iso3', columns='year', values='annual_anomaly_c').sort_index()


def _anomaly(values, reference):
    difference = values - reference
    if isinstance(difference, pd.Series):
        return difference.mask(difference.abs().le(ZERO_TOLERANCE_C), 0.)
    return 0. if abs(difference) <= ZERO_TOLERANCE_C else difference


def _validate_monthly(monthly: pd.DataFrame) -> pd.DataFrame:
    if not {'date', 'temperature_k'}.issubset(monthly.columns) or monthly.empty:
        raise ValueError('Nonempty validated monthly date/temperature_k data is required.')
    dates = monthly.date
    if not pd.api.types.is_datetime64_any_dtype(dates) or dates.isna().any():
        raise ValueError('Monthly dates must be nonmissing datetime values.')
    if (not dates.is_monotonic_increasing or dates.dt.to_period('M').duplicated().any()
            or not dates.dt.is_month_start.all() or not dates.eq(dates.dt.normalize()).all()):
        raise ValueError('Require ordered unique monthly timestamps on the first day at midnight.')
    if not pd.api.types.is_numeric_dtype(monthly.temperature_k):
        raise ValueError('Monthly temperatures must have a numeric dtype.')
    try:
        values = monthly.temperature_k.to_numpy(dtype=float, na_value=np.nan)
    except (ValueError, TypeError) as exc:
        raise ValueError('Monthly temperatures must be numeric.') from exc
    if np.isinf(values).any() or (values[np.isfinite(values)] < 0).any():
        raise ValueError('Monthly Kelvin values must be finite or missing, and nonnegative.')
    # Kelvin is canonical; reuse the existing conversion, never trust a stale C column.
    return clean_monthly(monthly)


def country_anomalies(monthly: pd.DataFrame, country: str, iso3: str,
                      config: FingerprintConfig | None = None) -> CountryAnomalies:
    config = config or FingerprintConfig()
    if not isinstance(iso3, str) or not re.fullmatch(r'[A-Z]{3}', iso3):
        raise ValueError('An explicit ISO-3 code is required.')
    if 'country' in monthly and not monthly.country.eq(country).all():
        raise ValueError('Monthly country labels conflict with the registry country.')
    clean = _validate_monthly(monthly)
    annual = annual_mean_temperatures(clean)
    complete = annual_trend_ready(annual)
    reference = complete.loc[complete.year.between(config.reference_start, config.reference_end)]
    expected = list(range(config.reference_start, config.reference_end + 1))
    if reference.year.tolist() != expected:
        raise ValueError(f'{country}: reference {config.reference_start}–{config.reference_end} requires every complete year; no reference years are dropped or imputed.')
    baseline = float(reference.temperature_c.mean())
    threshold = float(np.quantile(reference.temperature_c, config.warm_quantile, method='linear'))
    reference_meta = {'country': country, 'iso3': iso3,
                      'reference_start': config.reference_start, 'reference_end': config.reference_end,
                      'reference_definition': config.reference_definition,
                      'reference_year_count': len(reference), 'reference_mean_c': baseline,
                      'warm_quantile': config.warm_quantile, 'quantile_method': 'linear',
                      'warm_threshold_temperature_c': threshold,
                      'warm_threshold_anomaly_c': _anomaly(threshold, baseline)}

    # Reindex the target panel: unavailable years remain explicit, never a zero anomaly.
    target = annual.set_index('year').reindex(range(config.first_year, config.last_year + 1))
    target.index.name = 'year'
    target['valid_months'] = target.valid_months.fillna(0).astype(int)
    target['is_complete'] = target.valid_months.eq(12)
    target['annual_temperature_c'] = target.temperature_c.where(target.is_complete)
    target['annual_anomaly_c'] = _anomaly(target.annual_temperature_c, baseline)
    target['data_status'] = np.where(target.is_complete, 'complete',
                                     np.where(target.valid_months.eq(0), 'unavailable', 'incomplete'))
    target = target[['valid_months', 'is_complete', 'data_status', 'annual_temperature_c', 'annual_anomaly_c']].reset_index()
    for key, value in reference_meta.items():
        target[key] = value

    reference_months = clean.loc[clean.date.dt.year.between(config.reference_start, config.reference_end)]
    seasonal = reference_months.groupby(reference_months.date.dt.month).temperature_c.agg(['mean', 'count'])
    if seasonal.index.tolist() != list(range(1, 13)) or not seasonal['count'].eq(len(expected)).all():
        raise ValueError(f'{country}: every calendar month requires all reference observations.')
    seasonal.index.name = 'month'
    seasonal = seasonal.rename(columns={'mean': 'reference_month_mean_c', 'count': 'reference_month_count'}).reset_index()
    for key in ('country', 'iso3', 'reference_start', 'reference_end', 'reference_definition'):
        seasonal[key] = reference_meta[key]

    monthly_result = clean.copy()
    monthly_result['year'] = clean.date.dt.year
    monthly_result['month'] = clean.date.dt.month
    monthly_result = monthly_result.merge(seasonal, on='month', how='left', validate='many_to_one')
    monthly_result['monthly_anomaly_c'] = _anomaly(monthly_result.temperature_c, monthly_result.reference_month_mean_c)
    monthly_result['is_valid'] = monthly_result.temperature_c.notna()
    monthly_result['data_status'] = np.where(monthly_result.is_valid, 'valid', 'unavailable')
    return CountryAnomalies(target, monthly_result, reference_meta, seasonal)


def _registry_codes(registry: dict[str, dict]) -> dict[str, str]:
    if set(registry) != set(COUNTRIES):
        raise ValueError('The South America fingerprint requires all 12 registered countries.')
    if any(entry.get('status') == 'pending_confirmation' for entry in registry.values()):
        raise ValueError('Unresolved country mappings cannot enter the fingerprint.')
    codes = {country: entry.get('iso3') for country, entry in registry.items()}
    if (any(not isinstance(code, str) or not re.fullmatch(r'[A-Z]{3}', code) for code in codes.values())
            or len(set(codes.values())) != len(COUNTRIES)):
        raise ValueError('Require one unique ISO-3 code per registered country.')
    return codes


def build_fingerprint(monthly_by_country: dict[str, pd.DataFrame], registry: dict[str, dict],
                      config: FingerprintConfig | None = None) -> FingerprintDataset:
    """Build all country/year cells. Missing sources/baselines fail explicitly."""
    config = config or FingerprintConfig()
    codes = _registry_codes(registry)
    if set(monthly_by_country) != set(codes):
        raise ValueError('Monthly sources must match all 12 registry countries exactly.')
    results = [country_anomalies(monthly_by_country[country], country, codes[country], config)
               for country in sorted(codes, key=codes.get)]
    return FingerprintDataset(
        pd.concat([result.annual for result in results], ignore_index=True),
        pd.concat([result.monthly for result in results], ignore_index=True),
        pd.DataFrame([result.annual_reference for result in results]),
        pd.concat([result.monthly_references for result in results], ignore_index=True),
        config, pd.DataFrame(columns=['country', 'iso3', 'filename', 'sha256']))


def load_fingerprint(*, mapping_path: str | Path = MAPPING_PATH, raw_directory: str | Path = RAW_DIRECTORY,
                     config: FingerprintConfig | None = None) -> FingerprintDataset:
    registry = read_country_mapping(mapping_path)
    codes = _registry_codes(registry)
    datasets = {country: load_country(country, mapping_path=mapping_path, raw_directory=raw_directory)
                for country in sorted(codes, key=codes.get)}
    result = build_fingerprint({country: dataset.monthly for country, dataset in datasets.items()}, registry, config)
    result.sources = pd.DataFrame([{'country': country, 'iso3': codes[country],
                                    'filename': dataset.source.name, 'sha256': dataset.sha256}
                                   for country, dataset in datasets.items()])
    return result


def shared_warm_years(fingerprint: FingerprintDataset) -> pd.DataFrame:
    """Descriptive counts, not independent trials or a continental area average.

    Counts on incomplete panels describe observed countries only and explicitly
    retain the missing denominator. Equal-country means and widespread labels
    require every country; discovery functions omit incomplete panels.
    """
    rows = []
    total = len(fingerprint.annual_references)
    required = int(np.ceil(total * fingerprint.config.widespread_fraction))
    for year, panel in fingerprint.annual.groupby('year', sort=True):
        panel = panel.sort_values('iso3')
        observed = panel.loc[panel.is_complete & panel.annual_anomaly_c.notna()]
        positive = observed.annual_anomaly_c.gt(0)
        negative = observed.annual_anomaly_c.lt(0)
        exceed = observed.annual_temperature_c.gt(observed.warm_threshold_temperature_c + ZERO_TOLERANCE_C)
        full = len(observed) == total
        def countries(mask):
            return tuple(observed.loc[mask, 'iso3'])
        rows.append({'year': int(year), 'n_countries': total, 'n_available': len(observed),
                     'n_missing': total - len(observed), 'fully_observed': full,
                     'n_positive': int(positive.sum()), 'n_negative': int(negative.sum()),
                     'n_zero': int((~positive & ~negative).sum()), 'n_above_threshold': int(exceed.sum()),
                     'mean_country_anomaly_c': float(observed.annual_anomaly_c.mean()) if full else np.nan,
                     'weighting': 'equal country; 1/N per registered country; not area or population weighted',
                     'positive_countries': countries(positive), 'negative_countries': countries(negative),
                     'zero_countries': countries(~positive & ~negative),
                     'above_threshold_countries': countries(exceed),
                     'mean_contributing_countries': tuple(observed.iso3) if full else (),
                     'missing_countries': tuple(panel.loc[~panel.iso3.isin(observed.iso3), 'iso3']),
                     'widespread_required': required,
                     'widespread_warm': bool(exceed.sum() >= required) if full else None})
    return pd.DataFrame(rows)


def most_shared_years(summary: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Return every maximum-count tie, with chronological, deterministic order."""
    if metric not in ('n_positive', 'n_above_threshold'):
        raise ValueError('Choose n_positive or n_above_threshold.')
    eligible = summary.loc[summary.fully_observed]
    if eligible.empty:
        return eligible.copy()
    return eligible.loc[eligible[metric].eq(eligible[metric].max())].sort_values('year').reset_index(drop=True)


def widespread_warm_years(summary: pd.DataFrame) -> pd.DataFrame:
    return summary.loc[summary.fully_observed & summary.widespread_warm.eq(True)].sort_values(
        ['n_above_threshold', 'year'], ascending=[False, True]).reset_index(drop=True)


def largest_positive_anomalies(fingerprint: FingerprintDataset, limit: int = 5) -> pd.DataFrame:
    """Rank country/year departures from their own baselines, not temperatures.

    Exact anomaly ties use year then ISO-3 order. This ranking is descriptive,
    not a test that countries differ statistically or a warming-rate ranking.
    """
    if isinstance(limit, bool) or not isinstance(limit, Integral) or limit < 1:
        raise ValueError('The discovery limit must be a positive integer.')
    positive = fingerprint.annual.loc[fingerprint.annual.is_complete & fingerprint.annual.annual_anomaly_c.gt(0)]
    return positive.sort_values(['annual_anomaly_c', 'year', 'iso3'], ascending=[False, True, True]).head(limit).reset_index(drop=True)


def country_peak_anomalies(fingerprint: FingerprintDataset) -> pd.DataFrame:
    """Retain all tied positive peak years per country in the available window."""
    annual = fingerprint.annual.loc[fingerprint.annual.is_complete & fingerprint.annual.annual_anomaly_c.gt(0)]
    peak = annual.groupby('iso3').annual_anomaly_c.transform('max')
    return annual.loc[annual.annual_anomaly_c.eq(peak)].sort_values(
        ['annual_anomaly_c', 'year', 'iso3'], ascending=[False, True, True]).reset_index(drop=True)


def similar_country_patterns(fingerprint: FingerprintDataset) -> pd.DataFrame:
    """Pearson annual anomaly correlation and a first-difference sensitivity.

    Require a full common target window; no pairwise deletion or p-values.
    Shared trends can raise level correlation. First differences describe changes,
    not independent residuals, mechanisms, causation or event attribution.
    """
    matrix = fingerprint.anomaly_matrix
    rows = []
    for first, second in combinations(matrix.index, 2):
        left, right = matrix.loc[first].to_numpy(dtype=float), matrix.loc[second].to_numpy(dtype=float)
        valid = np.isfinite(left) & np.isfinite(right)
        paired_years = tuple(int(year) for year in matrix.columns[valid])
        status, correlation, change = 'ok', np.nan, np.nan
        if valid.sum() != len(left) or len(left) < 3:
            status = 'incomplete_window'
        elif np.ptp(left) <= ZERO_TOLERANCE_C or np.ptp(right) <= ZERO_TOLERANCE_C:
            status = 'constant_pattern'
        else:
            correlation = float(np.corrcoef(left, right)[0, 1])
            dl, dr = np.diff(left), np.diff(right)
            if np.ptp(dl) > ZERO_TOLERANCE_C and np.ptp(dr) > ZERO_TOLERANCE_C:
                change = float(np.corrcoef(dl, dr)[0, 1])
        rows.append({'iso3_a': first, 'iso3_b': second, 'paired_year_count': int(valid.sum()),
                     'paired_years': paired_years, 'correlation': correlation,
                     'change_correlation': change, 'status': status})
    return pd.DataFrame(rows).sort_values(['correlation', 'iso3_a', 'iso3_b'],
                                          ascending=[False, True, True], na_position='last').reset_index(drop=True)


def partial_year_anomalies(fingerprint: FingerprintDataset, year: int = 2026,
                           months: tuple[int, ...] = tuple(range(1, 10))) -> pd.DataFrame:
    """Compare the exact same chosen months; never apply a full-year threshold."""
    if isinstance(year, bool) or not isinstance(year, Integral):
        raise ValueError('Partial comparison year must be an integer.')
    if (not months or len(months) >= 12 or any(isinstance(m, bool) or not isinstance(m, Integral) or not 1 <= m <= 12 for m in months)
            or tuple(sorted(set(months))) != tuple(months)):
        raise ValueError('Choose 1–11 distinct, ordered calendar months for a partial comparison.')
    rows = []
    for reference in fingerprint.annual_references.itertuples():
        selected = fingerprint.monthly.loc[fingerprint.monthly.iso3.eq(reference.iso3)
                                            & fingerprint.monthly.year.eq(year)
                                            & fingerprint.monthly.month.isin(months)]
        seasonal = fingerprint.monthly_references.loc[fingerprint.monthly_references.iso3.eq(reference.iso3)
                                                       & fingerprint.monthly_references.month.isin(months)]
        complete = len(selected) == len(months) and selected.is_valid.all()
        baseline = float(seasonal.reference_month_mean_c.mean())
        value = float(selected.temperature_c.mean()) if complete else np.nan
        rows.append({'country': reference.country, 'iso3': reference.iso3, 'year': int(year),
                     'months': tuple(months), 'expected_month_count': len(months),
                     'valid_months': int(selected.temperature_c.count()), 'is_complete_selection': bool(complete),
                     'comparison_type': 'partial year; same calendar months only',
                     'reference_definition': reference.reference_definition,
                     'partial_temperature_c': value, 'reference_partial_mean_c': baseline,
                     'partial_anomaly_c': _anomaly(value, baseline)})
    return pd.DataFrame(rows)
