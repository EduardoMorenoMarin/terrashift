"""Known-answer climatologies, completeness, leakage, descriptive discovery and NASA integration."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from core.climate_fingerprint import (
    FingerprintConfig, build_fingerprint, country_anomalies, country_peak_anomalies,
    largest_positive_anomalies, load_fingerprint, most_shared_years, partial_year_anomalies,
    shared_warm_years, similar_country_patterns, widespread_warm_years,
)
from core.data_cleaning import annual_mean_temperatures
from core.region_data import COUNTRIES, load_country, read_country_mapping
from scripts.analyze_fingerprint import ROOT, sensitivity_fingerprint, write_analysis


@pytest.fixture(scope='module')
def registry():
    return read_country_mapping()


def monthly(offset=0.):
    dates = pd.date_range('2000-01-01', '2026-09-01', freq='MS')
    # Known annual means = 20 + offset + year_index; season has zero annual mean.
    temperature_c = 20 + offset + dates.year - 2000 + dates.month - 6.5
    return pd.DataFrame({'date': dates, 'temperature_k': temperature_c + 273.15})


@pytest.fixture
def panel():
    return {name: monthly(index * 3.) for index, name in enumerate(COUNTRIES)}


@pytest.fixture(scope='module')
def nasa():
    return load_fingerprint()


def test_annual_reference_mean_anomalies_quantile_and_metadata():
    result = country_anomalies(monthly(), 'Peru', 'PER')
    reference = result.annual_reference
    assert reference['reference_mean_c'] == pytest.approx(29.5)
    # n=20: zero-based interpolated sorted rank 19*.9=17.1, annual value 37.1.
    assert reference['warm_threshold_temperature_c'] == pytest.approx(37.1)
    assert reference['warm_threshold_anomaly_c'] == pytest.approx(7.6)
    assert reference['reference_year_count'] == 20
    assert reference['quantile_method'] == 'linear'
    assert reference['reference_start'] == 2000 and reference['reference_end'] == 2019
    assert len(result.annual) == 26
    for row in result.annual.itertuples():
        assert row.annual_temperature_c == pytest.approx(20 + row.year - 2000)
        assert row.annual_anomaly_c == pytest.approx(row.year - 2000 - 9.5)
        assert row.is_complete and row.valid_months == 12 and row.data_status == 'complete'
        assert row.country == 'Peru' and row.iso3 == 'PER'
        assert '2000–2019' in row.reference_definition
    reference_rows = result.annual.loc[result.annual.year.between(2000,2019)]
    assert reference_rows.annual_anomaly_c.mean() == pytest.approx(0, abs=1e-12)


def test_monthly_reference_removes_seasonality_and_matches_annual_anomalies():
    result = country_anomalies(monthly(), 'Peru', 'PER')
    assert len(result.monthly_references) == 12
    for row in result.monthly_references.itertuples():
        assert row.reference_month_count == 20
        assert row.reference_month_mean_c == pytest.approx(29.5 + row.month - 6.5)
    observed = result.monthly.loc[result.monthly.year.eq(2020)]
    assert np.ptp(observed.temperature_c) == pytest.approx(11.)
    assert observed.monthly_anomaly_c.to_numpy() == pytest.approx(np.repeat(10.5,12))
    for row in result.annual.itertuples():
        assert result.monthly.loc[result.monthly.year.eq(row.year)].monthly_anomaly_c.mean() == pytest.approx(row.annual_anomaly_c)
    grouped = result.monthly.loc[result.monthly.year.between(2000,2019)].groupby('month').monthly_anomaly_c.mean()
    assert grouped.to_numpy() == pytest.approx(np.zeros(12),abs=1e-12)


def test_absolute_country_temperature_offsets_do_not_change_anomalies_or_warm_counts(panel, registry):
    result = build_fingerprint(panel,registry)
    assert result.anomaly_matrix.shape == (12,26)
    assert len(result.annual) == 312
    for _, row in result.anomaly_matrix.iterrows():
        assert row.to_numpy() == pytest.approx(result.anomaly_matrix.iloc[0].to_numpy())
    annual = result.annual.loc[result.annual.year.eq(2024)]
    assert annual.annual_temperature_c.max() - annual.annual_temperature_c.min() == pytest.approx(33.)
    assert annual.annual_anomaly_c.nunique() == 1
    summary = shared_warm_years(result)
    assert summary.loc[summary.year.eq(2000), 'n_negative'].item() == 12
    assert summary.loc[summary.year.eq(2010), 'n_positive'].item() == 12
    assert summary.loc[summary.year.eq(2017), 'n_above_threshold'].item() == 0
    assert summary.loc[summary.year.eq(2018), 'n_above_threshold'].item() == 12
    assert summary.loc[summary.year.eq(2025), 'mean_country_anomaly_c'].item() == pytest.approx(15.5)


def test_counts_include_contributors_strict_threshold_ties_and_zeros(panel, registry):
    # A constant reference yields threshold zero; classify exact zero as neither sign nor exceedance.
    for name, frame in panel.items():
        frame['temperature_k'] = 293.15
    panel['Peru'].loc[panel['Peru'].date.dt.year.eq(2020), 'temperature_k'] += 2.
    panel['Brazil'].loc[panel['Brazil'].date.dt.year.eq(2020), 'temperature_k'] -= 1.
    result = build_fingerprint(panel,registry)
    row = shared_warm_years(result).set_index('year').loc[2020]
    assert (row.n_positive,row.n_negative,row.n_zero,row.n_above_threshold) == (1,1,10,1)
    assert row.positive_countries == row.above_threshold_countries == ('PER',)
    assert row.negative_countries == ('BRA',)
    assert len(row.zero_countries) == 10
    assert row.n_positive + row.n_negative + row.n_zero == row.n_available == 12
    assert row.mean_country_anomaly_c == pytest.approx(1/12)
    assert not row.widespread_warm and row.widespread_required == 9


def test_equal_country_weighting_is_not_pooled_month_or_area_weighting(panel, registry):
    # Baseline constant; one country contributes +12, all others zero -> +1 °C.
    for frame in panel.values(): frame['temperature_k'] = 293.15
    panel['Peru'].loc[panel['Peru'].date.dt.year.eq(2020), 'temperature_k'] += 12
    # Fake area/population metadata must never become weighting variables.
    altered = deepcopy(registry)
    altered['Peru']['area'] = 10**20
    altered['Peru']['population'] = 1
    result = build_fingerprint(panel, altered)
    row = shared_warm_years(result).set_index('year').loc[2020]
    assert row.mean_country_anomaly_c == pytest.approx(1.)
    assert len(row.mean_contributing_countries) == 12
    assert 'equal country' in row.weighting


def test_no_post_reference_data_leakage_even_when_future_values_are_huge():
    original = monthly()
    reference = country_anomalies(original,'Peru','PER')
    changed = original.copy(deep=True)
    changed.loc[changed.date.dt.year.gt(2019),'temperature_k'] += 1000
    changed['temperature_c'] = -999  # Stale derived column cannot contaminate canonical Kelvin conversion.
    result = country_anomalies(changed,'Peru','PER')
    assert result.annual_reference == reference.annual_reference
    pd.testing.assert_frame_equal(result.monthly_references,reference.monthly_references)
    pd.testing.assert_frame_equal(result.annual.loc[result.annual.year.le(2019)],reference.annual.loc[reference.annual.year.le(2019)])
    actual = result.annual.loc[result.annual.year.eq(2020),'annual_anomaly_c'].item()
    expected = reference.annual.loc[reference.annual.year.eq(2020),'annual_anomaly_c'].item()
    assert actual-expected == pytest.approx(1000.)
    pd.testing.assert_frame_equal(original,monthly())


def test_selected_analysis_window_does_not_refit_the_historical_reference():
    full = country_anomalies(monthly(),'Peru','PER')
    later = country_anomalies(monthly(),'Peru','PER',FingerprintConfig(first_year=2020,last_year=2025))
    assert later.annual_reference == full.annual_reference
    assert later.annual.year.tolist() == list(range(2020,2026))
    assert later.annual.annual_anomaly_c.tolist() == full.annual.loc[full.annual.year.ge(2020),'annual_anomaly_c'].tolist()


@pytest.mark.parametrize('defect', ['missing_month','missing_year','missing_value'])
def test_incomplete_reference_fails_without_silent_shortening_or_imputation(defect):
    frame = monthly()
    if defect == 'missing_month': frame = frame.drop(10)
    elif defect == 'missing_year': frame = frame.loc[frame.date.dt.year.ne(2005)]
    else: frame.loc[10,'temperature_k'] = np.nan
    with pytest.raises(ValueError,match='requires every complete year'):
        country_anomalies(frame,'Peru','PER')


@pytest.mark.parametrize('defect', ['missing_month','missing_year','missing_value'])
def test_incomplete_target_is_flagged_and_cannot_bias_panel_means_or_discoveries(panel,registry,defect):
    frame = panel['Argentina']
    selected = frame.index[frame.date.eq(pd.Timestamp('2022-03-01'))][0]
    if defect == 'missing_month': frame = frame.drop(selected)
    elif defect == 'missing_year': frame = frame.loc[frame.date.dt.year.ne(2022)]
    else: frame.loc[selected,'temperature_k'] = np.nan
    panel['Argentina'] = frame
    result = build_fingerprint(panel,registry)
    cell = result.annual.loc[result.annual.iso3.eq('ARG') & result.annual.year.eq(2022)].iloc[0]
    assert not cell.is_complete and pd.isna(cell.annual_anomaly_c) and pd.isna(cell.annual_temperature_c)
    assert cell.valid_months == (0 if defect=='missing_year' else 11)
    assert cell.data_status == ('unavailable' if defect=='missing_year' else 'incomplete')
    row = shared_warm_years(result).set_index('year').loc[2022]
    assert row.n_available == 11 and row.n_missing == 1 and row.n_positive == 11
    assert row.missing_countries == ('ARG',) and row.mean_contributing_countries == ()
    assert pd.isna(row.mean_country_anomaly_c) and row.widespread_warm is None
    assert 2022 not in most_shared_years(shared_warm_years(result),'n_positive').year.tolist()
    pairs = similar_country_patterns(result)
    pair = pairs.loc[pairs.iso3_a.eq('ARG')].iloc[0]
    assert pair.status == 'incomplete_window' and pair.paired_year_count == 25 and pd.isna(pair.correlation)


def test_absent_future_target_years_stay_unavailable_instead_of_zero(panel,registry):
    truncated = {country:frame.loc[frame.date.dt.year.le(2019)].copy() for country,frame in panel.items()}
    result = build_fingerprint(truncated,registry)
    future = result.annual.loc[result.annual.year.ge(2020)]
    assert len(future) == 72 and future.annual_anomaly_c.isna().all()
    summary = shared_warm_years(result).set_index('year').loc[2025]
    assert summary.n_available == 0 and summary.n_missing == 12
    assert summary.n_positive == 0 and pd.isna(summary.mean_country_anomaly_c)


def test_partial_2026_uses_identical_calendar_months_and_stays_out_of_annual_fingerprint(panel,registry):
    result = build_fingerprint(panel,registry)
    assert 2026 not in result.annual.year.unique()
    assert len(result.monthly.loc[result.monthly.year.eq(2026)]) == 108
    partial = partial_year_anomalies(result)
    assert partial.is_complete_selection.all() and partial.valid_months.eq(9).all()
    for row in partial.itertuples():
        assert row.partial_anomaly_c == pytest.approx(16.5)
        # Wrong full-year baseline would give 15.0 because of the season.
        full = result.annual_references.set_index('iso3').loc[row.iso3,'reference_mean_c']
        assert row.partial_temperature_c-full == pytest.approx(15.)
        assert row.reference_partial_mean_c == pytest.approx(full-1.5)
    assert not any('threshold' in column for column in partial)
    assert all(value == tuple(range(1,10)) for value in partial.months)


def test_partial_missing_month_is_unavailable_not_averaged_over_fewer_months(panel,registry):
    frame = panel['Peru']
    panel['Peru'] = frame.loc[~frame.date.eq(pd.Timestamp('2026-05-01'))].copy()
    result = build_fingerprint(panel,registry)
    partial = partial_year_anomalies(result).set_index('iso3')
    assert partial.loc['PER','valid_months'] == 8
    assert not partial.loc['PER','is_complete_selection']
    assert pd.isna(partial.loc['PER','partial_temperature_c']) and pd.isna(partial.loc['PER','partial_anomaly_c'])


@pytest.mark.parametrize('months', [(),tuple(range(1,13)),(1,1),(2,1),(0,1),(1,13),(True,2)])
def test_invalid_partial_month_sets(months,panel,registry):
    with pytest.raises(ValueError,match='calendar months'):
        partial_year_anomalies(build_fingerprint(panel,registry),months=months)


@pytest.mark.parametrize('defect', ['empty','duplicate_month','unsorted','bad_date','nonfinite','negative_kelvin','nonnumeric','country_label','iso3'])
def test_invalid_monthly_input_rejected(defect):
    frame = monthly()
    iso = 'PER'
    if defect=='empty': frame = frame.iloc[:0]
    elif defect=='duplicate_month': frame = pd.concat([frame.iloc[:1],frame],ignore_index=True)
    elif defect=='unsorted': frame = frame.iloc[::-1]
    elif defect=='bad_date': frame.loc[0,'date'] = pd.NaT
    elif defect=='nonfinite': frame.loc[0,'temperature_k'] = np.inf
    elif defect=='negative_kelvin': frame.loc[0,'temperature_k'] = -1
    elif defect=='nonnumeric': frame['temperature_k'] = frame.temperature_k.astype(str)
    elif defect=='country_label': frame['country'] = 'Brazil'
    else: iso = 'PE'
    with pytest.raises(ValueError):
        country_anomalies(frame,'Peru',iso)


@pytest.mark.parametrize('kwargs', [{'reference_start':2000.5},{'reference_end':True},
                                   {'reference_start':2019,'reference_end':2019}, {'first_year':2025,'last_year':2000},
                                   {'warm_quantile':0},{'warm_quantile':1},{'warm_quantile':np.nan},
                                   {'widespread_fraction':True},{'widespread_fraction':1}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError): FingerprintConfig(**kwargs)


@pytest.mark.parametrize('problem', ['missing_source','extra_source','missing_country','duplicate_iso','unresolved'])
def test_panel_requires_all_registered_countries_once(panel,registry,problem):
    altered = deepcopy(registry)
    if problem=='missing_source': panel.pop('Peru')
    elif problem=='extra_source': panel['Atlantis'] = monthly()
    elif problem=='missing_country': altered.pop('Peru')
    elif problem=='duplicate_iso': altered['Peru']['iso3'] = 'BRA'
    else: altered['Peru']['status'] = 'pending_confirmation'
    with pytest.raises(ValueError): build_fingerprint(panel,altered)


def test_discoveries_are_order_independent_keep_year_ties_and_use_descriptive_rule(panel,registry):
    result = build_fingerprint(panel,registry)
    summary = shared_warm_years(result)
    positive = most_shared_years(summary,'n_positive')
    exceed = most_shared_years(summary,'n_above_threshold')
    assert positive.year.tolist() == list(range(2010,2026))
    assert exceed.year.tolist() == list(range(2018,2026))
    assert widespread_warm_years(summary).year.tolist() == list(range(2018,2026))
    shuffled = replace(result,annual=result.annual.sample(frac=1,random_state=7))
    pd.testing.assert_frame_equal(shared_warm_years(shuffled),summary)
    pd.testing.assert_frame_equal(largest_positive_anomalies(shuffled),largest_positive_anomalies(result))
    pd.testing.assert_frame_equal(country_peak_anomalies(shuffled),country_peak_anomalies(result))
    pd.testing.assert_frame_equal(most_shared_years(summary.sample(frac=1,random_state=8),'n_positive'),positive)
    ranked = largest_positive_anomalies(result)
    assert ranked.year.eq(2025).all()
    assert ranked.iso3.tolist() == sorted(result.anomaly_matrix.index)[:5]
    with pytest.raises(ValueError): most_shared_years(summary,'mean_country_anomaly_c')
    with pytest.raises(ValueError): largest_positive_anomalies(result,limit=0)


def test_similarity_positive_negative_constant_and_change_sensitivity(panel,registry):
    result = build_fingerprint(panel,registry)
    annual = result.annual.copy(deep=True)
    pattern = np.sin(np.arange(26)) + np.arange(26)*.01
    for iso,values in [('ARG',pattern),('BOL',pattern*2+3),('BRA',-pattern),('CHL',np.zeros(26))]:
        annual.loc[annual.iso3.eq(iso),'annual_anomaly_c'] = values
    pairs = similar_country_patterns(replace(result,annual=annual)).set_index(['iso3_a','iso3_b'])
    assert pairs.loc[('ARG','BOL'),'correlation'] == pytest.approx(1)
    assert pairs.loc[('ARG','BOL'),'change_correlation'] == pytest.approx(1)
    assert pairs.loc[('ARG','BRA'),'correlation'] == pytest.approx(-1)
    assert pairs.loc[('ARG','CHL'),'status'] == 'constant_pattern'
    assert pd.isna(pairs.loc[('ARG','CHL'),'correlation'])
    assert len(pairs) == 66 and pairs.paired_year_count.eq(26).all()


def test_zero_variance_reference_never_creates_false_positive_anomalies(panel,registry):
    for frame in panel.values(): frame['temperature_k'] = 293.15
    result = build_fingerprint(panel,registry)
    assert result.annual.annual_anomaly_c.eq(0).all()
    summary = shared_warm_years(result)
    assert summary.n_positive.eq(0).all() and summary.n_above_threshold.eq(0).all()
    assert summary.n_zero.eq(12).all() and summary.mean_country_anomaly_c.eq(0).all()
    assert largest_positive_anomalies(result).empty and country_peak_anomalies(result).empty
    assert similar_country_patterns(result).status.eq('constant_pattern').all()


def test_real_nasa_references_independent_hand_calculations_source_integrity_and_panel(nasa,registry):
    assert nasa.anomaly_matrix.shape == (12,26)
    assert len(nasa.monthly) == 3852 and nasa.monthly.year.max() == 2026
    assert nasa.annual.year.max() == 2025 and nasa.annual.is_complete.all()
    assert nasa.annual_references.reference_year_count.eq(20).all()
    assert nasa.monthly_references.reference_month_count.eq(20).all()
    for country,entry in registry.items():
        source = ROOT / 'data/raw' / entry['filename']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == entry['sha256']
        data = load_country(country)
        # Independently compute annual means directly from the 240 reference months.
        reference = data.monthly.loc[data.monthly.date.dt.year.between(2000,2019)]
        annual = reference.groupby(reference.date.dt.year).temperature_c.mean()
        mean = float(annual.mean())
        sorted_values = sorted(annual.tolist())
        threshold = sorted_values[17]*.9 + sorted_values[18]*.1
        actual = nasa.annual_references.set_index('iso3').loc[entry['iso3']]
        assert actual.reference_mean_c == pytest.approx(mean)
        assert actual.warm_threshold_temperature_c == pytest.approx(threshold)
        for month in (1,9,12):
            expected = reference.loc[reference.date.dt.month.eq(month),'temperature_c'].mean()
            calculated = nasa.monthly_references.loc[nasa.monthly_references.iso3.eq(entry['iso3']) & nasa.monthly_references.month.eq(month),'reference_month_mean_c'].item()
            assert calculated == pytest.approx(expected)


def test_real_discoveries_and_equal_country_values_are_reproducible(nasa):
    summary = shared_warm_years(nasa).set_index('year')
    assert most_shared_years(summary.reset_index(),'n_positive').year.tolist() == [2020,2023,2024]
    assert most_shared_years(summary.reset_index(),'n_above_threshold').year.tolist() == [2023,2024]
    assert summary.loc[2024,'n_above_threshold'] == 12
    assert summary.loc[2020,'n_above_threshold'] == 9
    assert summary.loc[2025,'negative_countries'] == ('ECU',)
    assert summary.loc[2024,'mean_country_anomaly_c'] == pytest.approx(1.342896,abs=1e-6)
    top = largest_positive_anomalies(nasa).iloc[0]
    assert top.iso3 == 'GUY' and top.year == 2024
    assert top.annual_anomaly_c == pytest.approx(2.362710,abs=1e-6)
    partial = partial_year_anomalies(nasa)
    assert partial.partial_anomaly_c.gt(0).sum() == 12
    assert partial.partial_anomaly_c.mean() == pytest.approx(.781804,abs=1e-6)
    similarity = similar_country_patterns(nasa).iloc[0]
    assert (similarity.iso3_a,similarity.iso3_b) == ('PER','VEN')
    assert similarity.correlation == pytest.approx(.915467,abs=1e-6)


def test_sensitivity_reuses_loaded_observations_and_records_reference_dependence(nasa):
    with patch('core.climate_fingerprint.load_country',side_effect=AssertionError('unnecessary reload')):
        alternative = sensitivity_fingerprint(nasa)
    assert alternative.config.reference_end == 2009
    assert alternative.annual_references.reference_year_count.eq(10).all()
    primary = shared_warm_years(nasa).set_index('year')
    alternate = shared_warm_years(alternative).set_index('year')
    assert primary.loc[2025,'n_above_threshold'] == 7
    assert alternate.loc[2025,'n_above_threshold'] == 9
    pd.testing.assert_series_equal(similar_country_patterns(nasa).correlation,
                                   similar_country_patterns(alternative).correlation,rtol=1e-12,atol=1e-12)


def test_report_export_roundtrip_and_deterministic_artifact_hashes(nasa,tmp_path):
    output,report = tmp_path/'derived',tmp_path/'report.md'
    first = write_analysis(nasa,output,report)
    second = write_analysis(nasa,output,report)
    assert first == second
    assert len(pd.read_csv(output/'annual_fingerprint.csv')) == 312
    matrix = pd.read_csv(output/'annual_anomaly_matrix.csv',index_col='iso3')
    assert matrix.shape == (12,26) and '2026' not in matrix.columns
    partial = pd.read_csv(output/'partial_2026_january_september.csv')
    assert partial.valid_months.eq(9).all()
    summary = pd.read_csv(output/'shared_warm_years.csv')
    assert len(json.loads(summary.loc[summary.year.eq(2024),'above_threshold_countries'].item())) == 12
    for name,checksum in first['artifact_sha256'].items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest() == checksum
    text = report.read_text()
    assert '2000–2019' in text and 'not an absolute climate-risk' in text
    assert '1.342896' in text and '2.362710' in text
    assert '2026 is absent' in text
    assert 'not a hypothesis test' in text and '1/12' in text
    assert 'local heatwaves' in text and 'Baseline sensitivity' in text


def test_report_writer_refuses_raw_directory_outputs(nasa):
    with pytest.raises(ValueError,match='raw source'):
        write_analysis(nasa,ROOT/'data/raw',ROOT/'docs/report.md')


def test_cli_works_outside_project_directory(tmp_path):
    run = subprocess.run([sys.executable,str(ROOT/'scripts/analyze_fingerprint.py'),
                          '--output-directory',str(tmp_path/'derived'),'--report',str(tmp_path/'report.md')],
                         cwd=tmp_path,text=True,capture_output=True,timeout=30)
    assert run.returncode == 0, run.stderr
    assert 'Annual fingerprint: 312 cells' in run.stdout
    assert not run.stderr
