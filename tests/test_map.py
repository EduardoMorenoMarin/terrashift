"""Country joins, real/synthetic calculations, map semantics and UI regressions."""

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core.dashboard_data import prepare_period
from core.map_data import (load_boundaries, load_map_data, map_trend_table,
                           validate_geographic_join, validate_map_registry)
from core.map_charts import country_trend_figure
from core.region_data import load_country, read_country_mapping

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {'Argentina': 'ARG', 'Bolivia': 'BOL', 'Brazil': 'BRA', 'Chile': 'CHL',
            'Colombia': 'COL', 'Ecuador': 'ECU', 'Guyana': 'GUY', 'Paraguay': 'PRY',
            'Peru': 'PER', 'Suriname': 'SUR', 'Uruguay': 'URY', 'Venezuela': 'VEN'}


def test_all_twelve_explicit_iso_mappings_and_exact_geographic_join():
    registry = read_country_mapping()
    assert {name: entry['iso3'] for name, entry in registry.items()} == EXPECTED
    boundaries = load_boundaries(registry)
    assert len(boundaries['features']) == 12
    for country, code in EXPECTED.items():
        matched = [f for f in boundaries['features'] if f['properties']['iso3'] == code]
        assert len(matched) == 1
        assert matched[0]['properties']['name'] == country
        assert matched[0]['geometry']['type'] in ('Polygon', 'MultiPolygon')


@pytest.mark.parametrize('problem', ['missing', 'duplicate', 'extra', 'wrong_code', 'geometry'])
def test_invalid_geographic_joins_fail_closed(problem):
    registry = read_country_mapping()
    geo = load_boundaries(registry)
    if problem == 'missing':
        geo['features'].pop()
    elif problem == 'duplicate':
        geo['features'].append(deepcopy(geo['features'][0]))
    elif problem == 'extra':
        other = deepcopy(geo['features'][0])
        other['properties']['iso3'] = 'FRA'
        geo['features'].append(other)
    elif problem == 'wrong_code':
        geo['features'][0]['properties']['iso3'] = 'XXX'
    else:
        geo['features'][0]['geometry'] = None
    with pytest.raises(ValueError):
        validate_geographic_join(geo, registry)


@pytest.mark.parametrize('problem', ['missing_country', 'missing_code', 'duplicate', 'invalid_code'])
def test_invalid_map_registry(problem):
    registry = read_country_mapping()
    if problem == 'missing_country':
        registry.pop('Peru')
    elif problem == 'missing_code':
        registry['Peru'].pop('iso3')
    elif problem == 'duplicate':
        registry['Peru']['iso3'] = 'BRA'
    else:
        registry['Peru']['iso3'] = 'PE'
    with pytest.raises(ValueError):
        validate_map_registry(registry)


@pytest.mark.parametrize('start,end', [(2000, 2025), (2010, 2020)])
def test_all_real_map_trends_and_date_filtering_reuse_existing_analysis(start, end):
    table, geo = load_map_data(start, end)
    assert len(table) == len(geo['features']) == 12
    for row in table.to_dict('records'):
        expected = prepare_period(load_country(row['Country']).monthly, start, end).trend
        assert row['Trend (°C/decade)'] == expected.slope_per_decade
        assert row['Years analyzed'] == end - start + 1
        assert row['Analysis period'] == row['Selected period'] == f'{start}–{end}'


def synthetic_monthly(slope):
    year = np.arange(10)
    values = 20 + slope * year + np.sin(year) * .01
    dates = pd.date_range('2000-01-01', periods=120, freq='MS')
    return pd.DataFrame({'date': dates, 'temperature_c': np.repeat(values, 12),
                         'temperature_k': np.repeat(values, 12) + 273.15})


def test_synthetic_positive_negative_zero_and_unavailable_are_not_confused():
    registry = read_country_mapping()
    frames = {'Peru': synthetic_monthly(.2), 'Brazil': synthetic_monthly(-.1),
              'Chile': synthetic_monthly(0)}
    frames['Chile'][['temperature_c', 'temperature_k']] = [20., 293.15]
    original = {name: frame.copy(deep=True) for name, frame in frames.items()}
    table = map_trend_table(frames, registry, 2000, 2009).set_index('Country')
    assert table.loc['Peru', 'Trend (°C/decade)'] == pytest.approx(2, abs=.01)
    assert table.loc['Brazil', 'Trend (°C/decade)'] == pytest.approx(-1, abs=.01)
    assert table.loc['Chile', 'Trend (°C/decade)'] == pytest.approx(0, abs=1e-12)
    assert pd.isna(table.loc['Bolivia', 'Trend (°C/decade)'])
    assert table.loc['Bolivia', 'Notice'] == 'Temperature data is unavailable.'
    for name in frames:
        pd.testing.assert_frame_equal(frames[name], original[name])


@pytest.mark.parametrize('start,end', [(2000, 2000), (2000, 2001), (1990, 1999)])
def test_short_or_empty_period_keeps_twelve_unavailable_countries(start, end):
    table = map_trend_table({'Peru': synthetic_monthly(.2)}, read_country_mapping(), start, end)
    assert len(table) == 12
    assert table['Trend (°C/decade)'].isna().all()
    assert table.Notice.str.len().gt(0).all()
    figure = country_trend_figure(table, load_boundaries(read_country_mapping()), 'PER')
    assert len(figure.data) == 1
    assert not figure.data[0].showscale
    assert set(figure.data[0].locations) == set(EXPECTED.values())
    assert all(row[3] == 'Unavailable' for row in figure.data[0].customdata)
    assert all(row[2] == 'Unavailable' for row in figure.data[0].customdata)


@pytest.mark.parametrize('start,end', [(2025, 2000), (2000.5, 2025), (True, 2025)])
def test_invalid_dates_rejected_even_without_sources(start, end):
    with pytest.raises(ValueError):
        map_trend_table({}, read_country_mapping(), start, end)


def test_incomplete_endpoints_report_actual_fit_period_and_internal_gaps_unavailable():
    monthly = synthetic_monthly(.2)
    monthly.loc[0, ['temperature_c', 'temperature_k']] = np.nan
    table = map_trend_table({'Peru': monthly}, read_country_mapping(), 2000, 2009)
    peru = table.loc[table.Country.eq('Peru')].iloc[0]
    assert peru['Analysis period'] == '2001–2009'
    assert peru['Selected period'] == '2000–2009'
    monthly.loc[36, ['temperature_c', 'temperature_k']] = np.nan
    table = map_trend_table({'Peru': monthly}, read_country_mapping(), 2000, 2009)
    peru = table.loc[table.Country.eq('Peru')].iloc[0]
    assert pd.isna(peru['Trend (°C/decade)'])
    assert 'consecutive' in peru['Notice']


def test_one_unavailable_source_does_not_erase_other_countries():
    original = load_country
    def load(country, **kwargs):
        if country == 'Brazil':
            raise OSError('private source path')
        return original(country, **kwargs)
    with patch('core.map_data.load_country', side_effect=load):
        table, _ = load_map_data(2000, 2025)
    assert table['Trend (°C/decade)'].notna().sum() == 11
    assert pd.isna(table.loc[table.Country.eq('Brazil'), 'Trend (°C/decade)'].iloc[0])
    assert 'private' not in table.to_json()


def test_plot_joins_scale_hover_missing_fill_and_selection_outline():
    table, geo = load_map_data(2010, 2020)
    table.loc[table.Country.eq('Brazil'), 'Trend (°C/decade)'] = np.nan
    figure = country_trend_figure(table, geo, 'PER')
    missing, rates = figure.data
    assert set(missing.locations) == {'BRA'}
    assert len(rates.locations) == 11
    assert rates.type == 'choroplethmap'
    assert rates.featureidkey == 'properties.iso3'
    assert rates.geojson == geo
    assert rates.zmin == -rates.zmax
    assert rates.zmid == 0
    assert rates.zmax == table['Trend (°C/decade)'].abs().max()
    assert rates.colorscale[0][1] != rates.colorscale[-1][1]
    assert '°C/decade' in rates.colorbar.title.text
    for code, value, custom, width in zip(rates.locations, rates.z, rates.customdata, rates.marker.line.width):
        row = table.loc[table['ISO-3'].eq(code)].iloc[0]
        assert value == row['Trend (°C/decade)']
        assert list(custom[:3]) == [row.Country, '2010–2020', '2010–2020']
        assert custom[3] == f'{value:+.3f} °C/decade'
        assert width == (3 if code == 'PER' else 1)
    assert 'Unavailable' in missing.customdata[0][3]
    assert not missing.showscale
    assert figure.layout.map.style == 'white-bg'
    # JSON serialization validates a deliverable figure rather than just helper values.
    assert len(json.loads(figure.to_json())['data']) == 2


def map_spec(app):
    return next(json.loads(chart.proto.spec) for chart in app.get('plotly_chart')
                if json.loads(chart.proto.spec)['data'][0]['type'] == 'choroplethmap')


def test_map_and_explore_share_country_and_period_controls():
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert not app.exception and not app.error
    assert len(map_spec(app)['data'][0]['locations']) == 12
    app.selectbox(key='country').set_value('Brazil')
    app.selectbox(key='start_year').set_value(2010)
    app.selectbox(key='end_year').set_value(2020)
    app.run()
    assert not app.exception and not app.error
    trace = map_spec(app)['data'][0]
    assert trace['marker']['line']['width'][trace['locations'].index('BRA')] == 3
    assert all(row[1:3] == ['2010–2020', '2010–2020'] for row in trace['customdata'])
    assert any(s.value == 'Brazil · 2010–2020' for s in app.subheader)
    annual = map_spec(app)
    app.radio(key='frequency').set_value('Monthly').run()
    assert map_spec(app) == annual
    app.selectbox(key='start_year').set_value(2020).run()
    assert not app.exception and not app.error
    assert all(row[3] == 'Unavailable' for row in map_spec(app)['data'][0]['customdata'])
    assert any('Gray countries' in info.value for info in app.info)
    assert any('Short periods' in warning.value for warning in app.warning)


def test_map_failure_preserves_explore_and_hides_private_error():
    with patch('core.map_data.load_boundaries', side_effect=ValueError('/private/bad boundary')):
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert not app.exception and not app.error
    assert app.metric[0].value == '+0.370 °C/decade'
    assert any('map is temporarily unavailable' in info.value for info in app.info)
    assert not any('/private/' in info.value for info in app.info)


@pytest.mark.parametrize('value', [0., .4, -.4])
def test_single_direction_and_zero_maps_keep_zero_center(value):
    table = map_trend_table({}, read_country_mapping(), 2000, 2009)
    table['Trend (°C/decade)'] = value
    figure = country_trend_figure(table, load_boundaries(read_country_mapping()), 'PER')
    trace = figure.data[0]
    assert trace.zmid == 0
    assert trace.zmin == -trace.zmax
    assert trace.zmin < 0 < trace.zmax
    assert list(trace.z) == [value] * 12
    assert trace.showscale


def test_all_missing_temperatures_do_not_produce_zero_trend():
    monthly = synthetic_monthly(.2)
    monthly[['temperature_c', 'temperature_k']] = np.nan
    table = map_trend_table({'Peru': monthly}, read_country_mapping(), 2000, 2009)
    assert table['Trend (°C/decade)'].isna().all()
    assert table['Years analyzed'].eq(0).all()
