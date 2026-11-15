"""Phase 5F: reviewed availability, immutable source bytes and incomplete years."""

from copy import deepcopy
from dataclasses import replace
import csv
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core.country_comparison import comparison_table, prepare_comparison, country_colors
from core.dashboard_charts import temperature_figure, comparison_temperature_figure, warming_rate_figure
from core.dashboard_data import prepare_period, processed_csv
from core.data_cleaning import annual_mean_temperatures, clean_monthly, annual_trend_ready
from core.data_loader import load_data, resolve_original_source, resolve_reference_source
from core.dataset_audit import inspect_dataset
from core.i18n import country_name, t
from core.map_data import load_map_data
from core.map_charts import country_trend_figure
from core.region_data import (COUNTRIES, RegionDataError, expected_observation_months,
                              load_country, read_country_mapping, validate_dataset)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('country', COUNTRIES)
def test_updated_country_inventory_manifest_provenance_and_raw_integrity(country):
    entry = read_country_mapping()[country]
    source = ROOT / 'data/raw' / entry['filename']
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    result = load_country(country)
    audit = inspect_dataset(source, coverage=entry['coverage'])
    archived = json.loads((ROOT / 'metadata/history/phase_5d/country_mapping.json').read_text())
    previous = next(row for row in archived['countries'] if row['country'] == country)
    assert entry['sha256'] == result.sha256 == audit['sha256'] == before
    assert before != previous['sha256']
    assert entry['shape_identifier'] == audit['shape_identifier'] == previous['shape_identifier']
    assert entry['status'] == previous['status'] == 'user_confirmed'
    assert entry['evidence'] == previous['evidence']
    assert entry['iso3'] == previous['iso3']
    assert entry['csv_independently_verifies_country_identity'] is False
    assert entry['dataset_history'][-1]['sha256'] == previous['sha256']
    assert audit['data_status'] == 'VALID'
    assert len(result.monthly) == audit['monthly_observations'] == 321
    assert result.monthly.date.min() == pd.Timestamp('2000-01-01')
    assert result.monthly.date.max() == pd.Timestamp('2026-09-01')
    assert result.monthly.date.dt.to_period('M').tolist() == list(pd.period_range('2000-01','2026-09',freq='M'))
    assert result.monthly.country.eq(country).all()
    for field in ('malformed_records','invalid_timestamps','invalid_numeric_values','blank_temperatures',
                  'fill_values','nonfinite_temperatures','duplicate_timestamps','duplicate_months'):
        assert audit[field] == 0
    assert audit['missing_months'] == audit['unexpected_months'] == []
    assert audit['complete_year_list'] == list(range(2000,2026))
    assert audit['incomplete_years'] == [{'year':2026,'valid_months':9}]
    assert audit['missing_requested_months'] == audit['reviewed_unavailable_requested_months'] == ['2026-10']
    assert result.missing_months == ()
    assert result.unavailable_requested_months == ('2026-10',)
    assert audit['data_id'] == 'M2TMNXSLV_5_12_4_T2M'
    assert audit['units_explicit_in_export'] is False
    assert 'documentation' in audit['units']
    partial = result.annual.loc[result.annual.year.eq(2026)].iloc[0]
    assert partial.valid_months == 9 and not partial.is_complete
    assert len(result.complete_annual) == 26
    full = prepare_period(result.monthly,2000,2026)
    baseline = prepare_period(result.monthly,2000,2025)
    assert full.trend == baseline.trend
    assert full.trend.years == tuple(range(2000,2026))
    assert len(temperature_figure(full,'Monthly').data[0].y) == 321
    annual = temperature_figure(full,'Annual')
    assert pd.isna(annual.data[0].y[-1])
    assert annual.data[1].x[-1] == 2025
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_inventory_snapshot_matches_every_current_file_and_missing_request_is_not_hidden():
    doc = json.loads((ROOT / 'metadata/region_inventory.json').read_text())
    registry = read_country_mapping()
    assert len(doc['files']) == 12
    assert {row['filename'] for row in doc['files']} == {entry['filename'] for entry in registry.values()}
    for row in doc['files']:
        assert row['monthly_observations'] == 321
        assert row['expected_coverage'] == ['2000-01','2026-09']
        assert row['missing_requested_months'] == ['2026-10']
        assert row['warnings']
        assert row['coverage_review']
    assert len({(row['first_date'],row['last_date']) for row in doc['files']}) == 1


def test_peru_uses_observed_filename_and_current_checksum_without_rewriting_history():
    entry = read_country_mapping()['Peru']
    assert entry['filename'].endswith('_SURI_PER.csv')
    assert entry['shape_identifier'] == 'state_dept_countries_2017/shp_174'
    provenance = json.loads((ROOT / 'metadata/dataset_provenance.json').read_text())
    old = json.loads((ROOT / 'metadata/history/phase_5d/dataset_provenance.json').read_text())
    for key,value in old.items():
        assert provenance[key] == value
    assert resolve_reference_source() == load_country('Peru').source
    assert provenance['current_dataset']['sha256'] == entry['sha256']
    assert provenance['current_dataset']['coverage']['observations'] == 321
    with pytest.raises(ValueError,match='found 0'):
        resolve_original_source()  # Original historical bytes are no longer in data/raw.


def test_unreviewed_request_shortage_is_rejected_and_reviewed_shortage_is_exact():
    entry = read_country_mapping()['Peru']
    loaded = load_data(resolve_reference_source())
    assert loaded.missing_months == ('2026-10',)
    with pytest.raises(RegionDataError,match='coverage|missing months'):
        validate_dataset(loaded)
    assert validate_dataset(loaded,coverage=entry['coverage'])['variable'] == 'T2M'
    assert inspect_dataset(loaded.source)['data_status'] == 'INVALID'
    assert inspect_dataset(loaded.source,coverage=entry['coverage'])['data_status'] == 'VALID'


@pytest.mark.parametrize('problem', ['count','bool_count','start','end','unlisted_shortage','extra_shortage','missing_review'])
def test_reviewed_coverage_cannot_silently_accept_conflicting_dates_or_counts(problem):
    coverage = deepcopy(read_country_mapping()['Peru']['coverage'])
    if problem == 'count': coverage['observations'] = 320
    elif problem == 'bool_count': coverage['observations'] = True
    elif problem == 'start': coverage['start_month'] = '2000-00'
    elif problem == 'end': coverage['end_month'] = '1999-12'
    elif problem == 'unlisted_shortage': coverage['unavailable_requested_months'] = []
    elif problem == 'extra_shortage': coverage['unavailable_requested_months'] = ['2026-10','2026-11']
    else: coverage['coverage_note'] = ''
    with pytest.raises(RegionDataError,match='coverage'):
        expected_observation_months(coverage)


@pytest.mark.parametrize('key,value', [('Units','Celsius'),('Collection','OTHER'),('Variable','T10M'),
                                     ('Version','5.12.3'),('User End Date','2026-09-30T23:59:59Z')])
def test_conflicting_source_metadata_is_not_accepted(key,value):
    entry = read_country_mapping()['Peru']
    loaded = load_data(resolve_reference_source())
    metadata = {**loaded.metadata,key:value}
    with pytest.raises(RegionDataError):
        validate_dataset(replace(loaded,metadata=metadata),coverage=entry['coverage'])


def test_internal_gap_is_rejected_even_with_a_reviewed_terminal_shortage():
    loaded = load_data(resolve_reference_source())
    coverage = read_country_mapping()['Peru']['coverage']
    broken = loaded.observations.loc[~loaded.observations.date.eq(pd.Timestamp('2020-01-01'))].copy()
    with pytest.raises(RegionDataError,match='coverage|missing months'):
        validate_dataset(replace(loaded,observations=broken,missing_months=('2020-01','2026-10')),coverage=coverage)


def test_future_extension_uses_metadata_not_fixed_terminal_year_or_observation_count(tmp_path):
    # A synthetic full-request export, independent of the current reviewed release.
    path = tmp_path / 'future.csv'
    dates = pd.date_range('2000-01-01','2027-02-01',freq='MS')
    with path.open('w',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerows([
            ['Title:','Synthetic monthly 2-meter air temperature'],
            ['User Start Date:','2000-01-01T00:00:00Z'],
            ['User End Date:','2027-02-28T23:59:59Z'],
            ['URL to Reproduce Results:','https://giovanni.gsfc.nasa.gov/giovanni/#service=ArAvTs&starttime=2000-01-01T00:00:00Z&endtime=2027-02-28T23:59:59Z&shape=synthetic/Peru&data=M2TMNXSLV_5_12_4_T2M'],
            ['Units:','Kelvin'],
            ['Fill Value (mean_M2TMNXSLV_5_12_4_T2M):','1000000000000000'],
            ['time','mean_M2TMNXSLV_5_12_4_T2M'],
            *[[f'{date:%Y-%m-%d} 00:00:00',290+i*.001] for i,date in enumerate(dates)]])
    loaded = load_data(path)
    validate_dataset(loaded)
    annual = annual_mean_temperatures(clean_monthly(loaded.observations))
    assert len(loaded.observations) == len(dates)
    assert annual_trend_ready(annual).year.iloc[-1] == 2026
    assert annual.iloc[-1].valid_months == 2 and not annual.iloc[-1].is_complete
    assert inspect_dataset(path)['data_status'] == 'VALID'


def test_comparisons_map_and_exports_use_the_same_complete_years():
    periods = prepare_comparison(['Peru','Brazil'],2000,2026)
    colors = country_colors(list(COUNTRIES))
    annual = comparison_temperature_figure(periods,'Annual',colors)
    monthly = comparison_temperature_figure(periods,'Monthly',colors)
    rates = warming_rate_figure(periods,colors)
    table = comparison_table(periods)
    for country,trace,line,rate in zip(periods,annual.data,monthly.data,rates.data):
        assert pd.isna(trace.y[-1])
        assert sum(pd.notna(list(trace.y))) == 26
        assert len(line.x) == 321 and line.x[-1] == pd.Timestamp('2026-09-01')
        assert rate.customdata[0][2] == '2000–2025'
        assert rate.x[0] == periods[country].trend.slope_per_decade
    assert table['Analysis period'].eq('2000–2025').all()
    assert table['Years analyzed'].eq(26).all()
    map_table,geo = load_map_data(2000,2026)
    assert len(geo['features']) == len(map_table) == 12
    assert map_table['Selected period'].eq('2000–2026').all()
    assert map_table['Analysis period'].eq('2000–2025').all()
    assert map_table['Years analyzed'].eq(26).all()
    assert map_table.Notice.eq(t('notice.partial_year')).all()
    for row in map_table.to_dict('records'):
        reference = prepare_period(load_country(row['Country']).monthly,2000,2025)
        assert row['Trend (°C/decade)'] == reference.trend.slope_per_decade
    period = periods['Peru']
    from io import BytesIO
    exported_months = pd.read_csv(BytesIO(processed_csv(period,'Monthly')))
    exported_years = pd.read_csv(BytesIO(processed_csv(period,'Annual')))
    assert len(exported_months) == 321
    assert exported_years.iloc[-1].year == 2026
    assert not exported_years.iloc[-1].is_complete and exported_years.iloc[-1].valid_months == 9


def test_only_2026_has_monthly_values_without_annual_points_or_trends():
    periods = prepare_comparison(['Peru','Brazil'],2026,2026)
    for period in periods.values():
        assert len(period.monthly) == 9
        assert period.complete_annual.empty and period.trend is None
        assert all(pd.isna(value) for value in temperature_figure(period,'Annual').data[0].y)
        assert len(temperature_figure(period,'Monthly').data[0].y) == 9
    table = comparison_table(periods)
    assert table['Analysis period'].eq('Unavailable').all()
    assert table['Years analyzed'].eq(0).all()
    map_table,geo = load_map_data(2026,2026)
    assert map_table['Trend (°C/decade)'].isna().all()
    assert map_table['Analysis period'].eq('Unavailable').all()
    assert not country_trend_figure(map_table,geo,'PER').data[0].showscale


@pytest.mark.parametrize('lang', ['en','es'])
def test_dashboard_coverage_monthly_2026_annual_exclusion_and_language_switch(lang):
    app = AppTest.from_file(str(ROOT / 'app.py'),default_timeout=30)
    app.session_state['language'] = lang
    app.run()
    assert not app.exception and not app.error
    assert app.selectbox(key='end_year').value == 2026
    assert app.metric[-1].value == '26'
    coverage = '\n'.join(element.value for element in app.caption)
    assert ('September 2026' if lang=='en' else 'septiembre 2026') in coverage
    assert '2000–2025' in coverage
    assert ('October 2026' if lang=='en' else 'octubre 2026') in coverage
    assert not any('user_confirmed' in element.value for element in app.caption)
    app.multiselect(key='compare_countries').set_value(['Peru','Brazil'])
    app.radio(key='frequency').set_value('Monthly')
    app.selectbox(key='start_year').set_value(2026).run()
    assert not app.exception and not app.error
    assert not app.metric
    assert any(t('notice.insufficient',lang) == info.value for info in app.info)
    monthly_specs = [json.loads(chart.proto.spec) for chart in app.get('plotly_chart')
                     if json.loads(chart.proto.spec)['data'][0]['type']=='scatter']
    assert monthly_specs and all(len(trace['x'])==9 for spec in monthly_specs for trace in spec['data'])
    app.session_state['active_tab'] = t('section.compare',lang)
    app.run()
    target = 'es' if lang=='en' else 'en'
    with patch('core.region_data.load_country',side_effect=AssertionError('unexpected reload')):
        app.selectbox(key='language').set_value(target).run()
    assert not app.exception and not app.error
    assert app.session_state['analysis_section'] == 'compare'
    assert app.selectbox(key='start_year').value == app.selectbox(key='end_year').value == 2026
    app.radio(key='frequency').set_value('Annual').run()
    assert not app.exception and not app.error
    assert not app.metric
    assert any(t('compare.annual_complete',target)==caption.value for caption in app.caption)
