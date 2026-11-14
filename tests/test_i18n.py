"""Catalog contracts and bilingual rendering without changing scientific results."""

import ast
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import re
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core import i18n
from core.i18n import (catalogs, country_name, month_labels, placeholders, plural, t,
                       TranslationError, validate_catalogs)
from core.country_comparison import comparison_table, interpret_comparison, prepare_comparison, country_colors
from core.dashboard_charts import temperature_figure, comparison_temperature_figure, warming_rate_figure
from core.dashboard_copy import chart_config, display_temperature_data, localize_notice, localize_table
from core.dashboard_data import interpret_trend, prepare_period, processed_csv
from core.dashboard_state import source_signature
from core.map_charts import country_trend_figure
from core.map_data import load_boundaries, load_map_data, map_trend_table
from core.region_data import COUNTRIES, load_country, read_country_mapping

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_parity_nonempty_values_and_all_templates_interpolate():
    raw = {lang: json.loads((ROOT / 'locales' / f'{lang}.json').read_text()) for lang in ('en', 'es')}
    validate_catalogs(raw)
    assert set(raw['en']) == set(raw['es'])
    assert len(raw['en']) >= 200
    for lang, catalog in raw.items():
        for key, value in catalog.items():
            fields = placeholders(value)
            variables = {name: 1.25 if spec else 'example' for name, (spec, _) in fields.items()}
            rendered = t(key, lang, **variables)
            assert rendered.strip(), key


@pytest.mark.parametrize('problem', ['missing_key', 'extra_key', 'missing_language', 'wrong_placeholder',
                                     'wrong_format', 'empty_value', 'nonstring_value'])
def test_invalid_catalogs_are_rejected(problem):
    data = deepcopy(catalogs())
    if problem == 'missing_key':
        del data['es']['app.heading']
    elif problem == 'extra_key':
        data['es']['extra'] = 'Extra'
    elif problem == 'missing_language':
        del data['es']
    elif problem == 'wrong_placeholder':
        data['es']['common.country_period'] = '{pais} · {start}–{end}'
    elif problem == 'wrong_format':
        data['es']['common.interval'] = '{low:+.2f} a {high:+.3f}'
    elif problem == 'empty_value':
        data['es']['app.heading'] = ' '
    else:
        data['es']['app.heading'] = 5
    with pytest.raises(TranslationError):
        validate_catalogs(data)


@pytest.mark.parametrize('call', [lambda: t('not.a.key'), lambda: t('app.title', 'fr'),
                                 lambda: t('map.heading', start=2000),
                                 lambda: t('map.heading', start=2000, end=2025, unexpected=True),
                                 lambda: t('common.interval', low='invalid', high=2.)])
def test_missing_keys_languages_and_interpolation_errors_are_explicit(call):
    with pytest.raises(TranslationError):
        call()


@pytest.mark.parametrize('template', ['{', '{0}', '{value.name}', '{value:{width}}'])
def test_malformed_or_unstable_placeholders_rejected(template):
    with pytest.raises(TranslationError):
        placeholders(template)


def test_duplicate_json_keys_rejected(tmp_path):
    for lang in ('en', 'es'):
        (tmp_path / f'{lang}.json').write_text('{"duplicate":"a","duplicate":"b"}')
    catalogs.cache_clear()
    try:
        with patch.object(i18n, 'LOCALES', tmp_path), pytest.raises(TranslationError, match='Duplicate'):
            catalogs()
    finally:
        catalogs.cache_clear()


def test_static_translation_references_exist_and_ui_copy_is_not_embedded():
    for path in [ROOT / 'app.py', *ROOT.glob('core/*.py')]:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('tr', 't'):
                if node.args and isinstance(node.args[0], ast.Constant):
                    assert node.args[0].value in catalogs()['en'], (path, node.lineno)
            if (path.name == 'app.py' and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ('caption', 'subheader', 'header', 'title', 'info', 'warning', 'error', 'write', 'expander')
                    and node.args):
                assert not isinstance(node.args[0], (ast.Constant, ast.JoinedStr)), (path, node.lineno)


def test_country_display_names_leave_registry_and_iso_identifiers_unchanged():
    expected = ['Argentina', 'Bolivia', 'Brasil', 'Chile', 'Colombia', 'Ecuador',
                'Guyana', 'Paraguay', 'Perú', 'Surinam', 'Uruguay', 'Venezuela']
    before = read_country_mapping()
    assert [country_name(country, 'es') for country in COUNTRIES] == expected
    assert [country_name(country, 'en') for country in COUNTRIES] == list(COUNTRIES)
    assert before == read_country_mapping()


@pytest.mark.parametrize('count,en,es', [(0, '0 complete years', '0 años completos'),
                                       (1, '1 complete year', '1 año completo'),
                                       (2, '2 complete years', '2 años completos')])
def test_grammatical_count_forms(count, en, es):
    assert plural('count.complete_year', count) == en
    assert plural('count.complete_year', count, 'es') == es
    assert ('Falta ' if count == 1 else 'Faltan ') in plural('count.missing_month', count, 'es')


def test_concurrent_translations_do_not_share_language_state():
    languages = ['en', 'es'] * 30
    with ThreadPoolExecutor(max_workers=4) as pool:
        rendered = list(pool.map(lambda lang: t('metric.trend', lang), languages))
    assert rendered == ['Temperature trend', 'Tendencia de temperatura'] * 30


@pytest.fixture(scope='module')
def periods():
    return prepare_comparison(['Peru', 'Brazil'], 2010, 2020)


@pytest.mark.parametrize('frequency', ['Annual', 'Monthly'])
def test_localized_charts_preserve_values_and_use_localized_dates(periods, frequency):
    period = periods['Peru']
    en = temperature_figure(period, frequency)
    es = temperature_figure(period, frequency, lang='es')
    assert es.layout.yaxis.title.text == 'Temperatura del aire (°C)'
    assert list(es.data[0].x) == list(en.data[0].x)
    assert list(es.data[0].y) == list(en.data[0].y)
    assert es.layout.uirevision == en.layout.uirevision
    assert es.data[0].name == t('chart.annual' if frequency == 'Annual' else 'chart.monthly', 'es')
    if frequency == 'Annual':
        assert es.data[1].name == 'Tendencia lineal'
        assert es.data[0].customdata[0][1] == 'Sí'
        assert 'Meses disponibles' in es.data[0].hovertemplate
    else:
        assert es.data[0].customdata[0][0] == 'enero 2010'
        assert es.layout.xaxis.ticktext[0] == 'ene 2010'
        assert es.layout.xaxis.hoverformat == '%Y-%m'
    colors = country_colors(list(COUNTRIES))
    compared = comparison_temperature_figure(periods, frequency, colors, lang='es')
    assert compared.layout.uirevision == comparison_temperature_figure(periods, frequency, colors).layout.uirevision
    assert [trace.name for trace in compared.data] == ['Perú', 'Brasil']
    for trace, (_, selected) in zip(compared.data, periods.items()):
        assert list(trace.y) == (selected.annual if frequency == 'Annual' else selected.monthly).temperature_c.tolist()
        assert trace.name in trace.hovertemplate
    rate_en = warming_rate_figure(periods, colors)
    rate_es = warming_rate_figure(periods, colors, lang='es')
    assert rate_es.layout.uirevision == rate_en.layout.uirevision
    for en_trace, es_trace in zip(rate_en.data, rate_es.data):
        assert list(en_trace.x) == list(es_trace.x)
        assert list(en_trace.error_x.array) == list(es_trace.error_x.array)
        assert list(en_trace.error_x.arrayminus) == list(es_trace.error_x.arrayminus)
        assert 'Intervalo de confianza del 95%' in es_trace.hovertemplate
        assert 'Valor p' in es_trace.hovertemplate
    assert list(rate_es.layout.yaxis.categoryarray) == ['Perú', 'Brasil']


def test_plotly_configuration_translates_native_controls():
    config = chart_config('es', scrollZoom=False)
    assert config['locale'] == 'es'
    assert config['scrollZoom'] is False
    assert config['locales']['es']['dictionary']['Download plot as a PNG'] == 'Descargar gráfico como PNG'
    assert config['locales']['es']['dictionary']['Zoom out'] == 'Alejar'
    assert chart_config()['locale'] == 'en'


def test_map_translates_all_displayed_fields_and_preserves_geometry_and_results():
    table, boundaries = load_map_data(2010, 2020)
    original = table.copy(deep=True)
    en = country_trend_figure(table, boundaries, 'PER')
    es = country_trend_figure(table, boundaries, 'PER', lang='es')
    assert es.data[0].colorbar.title.text == 'Tendencia anual<br>°C/década'
    assert es.data[0].hovertemplate == t('map.hover', 'es')
    assert list(en.data[0].z) == list(es.data[0].z)
    assert list(en.data[0].locations) == list(es.data[0].locations)
    assert en.data[0].geojson == es.data[0].geojson
    index = list(es.data[0].locations).index('PER')
    assert es.data[0].customdata[index][0] == 'Perú'
    assert list(es.data[0].customdata[index][1:3]) == ['2010–2020', '2010–2020']
    assert '°C/década' in es.data[0].customdata[index][3]
    pd.testing.assert_frame_equal(table, original)
    missing = map_trend_table({}, read_country_mapping(), 2025, 2025)
    figure = country_trend_figure(missing, boundaries, 'PER', lang='es')
    assert all(list(row[2:4]) == ['No disponible', 'No disponible'] for row in figure.data[0].customdata)
    assert all(row[4] == 'Los datos de temperatura no están disponibles.' for row in figure.data[0].customdata)
    assert not figure.data[0].showscale


@pytest.mark.parametrize('frequency', ['Annual', 'Monthly'])
def test_tables_localize_labels_status_countries_without_mutation_or_numeric_changes(periods, frequency):
    period = periods['Peru']
    before = period.annual.copy(deep=True)
    exported = processed_csv(period, frequency)
    display = display_temperature_data(period, frequency, lang='es')
    if frequency == 'Monthly':
        assert display['País'].eq('Perú').all()
    assert display['Temperatura (°C)'].tolist() == (period.annual if frequency == 'Annual' else period.monthly).temperature_c.tolist()
    if frequency == 'Annual':
        assert display['Año completo'].eq('Sí').all()
    en = comparison_table(periods)
    es = comparison_table(periods, lang='es')
    assert es['País'].tolist() == ['Perú', 'Brasil']
    for key in ('column.trend', 'column.p', 'column.r2', 'column.years'):
        assert es[t(key, 'es')].tolist() == en[t(key)].tolist()
    assert ' a ' in es[t('column.ci', 'es')].iloc[0]
    pd.testing.assert_frame_equal(period.annual, before)
    assert processed_csv(period, frequency) == exported


def test_short_map_table_and_all_notices_are_localized():
    table, _ = load_map_data(2024, 2025)
    translated = localize_table(table, 'es')
    assert translated['Período de análisis'].eq('No disponible').all()
    assert translated['Observación'].eq(t('notice.insufficient', 'es')).all()
    for key in ('notice.no_data', 'notice.insufficient', 'notice.gaps', 'notice.source'):
        assert localize_notice(t(key), 'es') == t(key, 'es')
    with pytest.raises(TranslationError):
        localize_notice('Unexpected unregistered public text', 'es')


def synthetic(values):
    dates = pd.date_range('2000-01-01', periods=12 * len(values), freq='MS')
    monthly = pd.DataFrame({'date': dates, 'temperature_c': np.repeat(values, 12),
                            'temperature_k': np.repeat(values, 12) + 273.15})
    return prepare_period(monthly, 2000, 2000 + len(values) - 1)


@pytest.mark.parametrize('values,expected', [
    (20 + .2 * np.arange(10) + np.sin(np.arange(10)) * .01, 'calentamiento'),
    (20 - .2 * np.arange(10) + np.sin(np.arange(10)) * .01, 'enfriamiento'),
    (np.full(10, 20.), 'ausencia de cambio lineal estimado'),
    ([20., 21., 19., 20., 21., 19., 20., 21., 19., 20.], 'dirección del cambio sigue siendo incierta'),
])
def test_dynamic_trend_interpretations_preserve_estimates_and_conclusions(values, expected):
    result = synthetic(values).trend
    original = deepcopy(result)
    text = interpret_trend(result, lang='es')
    assert expected in text
    assert f'{result.slope_per_decade:+.3f}' in text
    assert f'{result.first_to_last_difference:+.3f}' in text
    assert '2000 y 2009' in text
    assert '10 años completos' in text
    if result.hac.confidence_interval_per_decade:
        assert 'intervalo de confianza del 95%' in text
        for value in result.hac.confidence_interval_per_decade:
            assert f'{value:+.3f}' in text
        assert ('evidencia estadística' in text) == result.hac.significant
    else:
        assert 'valores p no están disponibles' in text
    assert result == original
    dependent = replace(result, diagnostics=replace(result.diagnostics, autocorrelation_detected=True))
    assert t('interpret.dependence', 'es') in interpret_trend(dependent, lang='es')


@pytest.mark.parametrize('countries', [['Peru'], ['Peru', 'Brazil']])
def test_comparison_interpretations_work_for_one_and_multiple_countries(countries):
    warming = synthetic(20 + .2 * np.arange(10) + np.sin(np.arange(10)) * .01)
    cooling = synthetic(20 - .1 * np.arange(10) + np.sin(np.arange(10)) * .01)
    periods = dict(zip(countries, [warming, cooling]))
    text = interpret_comparison(periods, lang='es')
    assert 'Calentamiento estimado: **Perú**' in text
    assert 'Evidencia estadística de una tendencia individual' in text
    if 'Brazil' in countries:
        assert 'Enfriamiento estimado: **Brasil**' in text
    for country in countries:
        assert country_name(country, 'es') in text
    assert t('interpret_compare.caution', 'es') in text
    unavailable = synthetic([20., 21.])
    text = interpret_comparison({name: unavailable for name in countries}, lang='es')
    assert 'No se puede evaluar la incertidumbre de la tendencia en' in text
    nonsignificant = synthetic([20.,21.,19.,20.,21.,19.,20.,21.,19.,20.])
    assert 'dirección del cambio sigue siendo incierta' in interpret_comparison({'Peru': nonsignificant}, lang='es')
    assert 'Sin cambio lineal estimado' in interpret_comparison({'Peru': synthetic(np.full(10,20.))}, lang='es')


def new_app(lang='en'):
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30)
    app.session_state['language'] = lang
    return app


def public_text(app):
    parts = []
    for kind in ('caption','header','subheader','title','markdown','info','warning','error','metric','expander','tab',
                 'selectbox','multiselect','radio','toggle','download_button'):
        for element in app.get(kind):
            for attr in ('value','label','help','options'):
                try:
                    value = getattr(element, attr)
                except (AttributeError, KeyError, NotImplementedError):
                    continue
                if isinstance(value, (str,list,tuple)):
                    parts.append(str(value))
    parts.extend(frame.value.to_json(force_ascii=False, date_format='iso') for frame in app.dataframe)
    for chart in app.get('plotly_chart'):
        spec = json.loads(chart.proto.spec)
        for trace in spec['data']:
            trace.pop('geojson',None)  # Retained upstream metadata is not a displayed label.
        parts.append(json.dumps(spec,ensure_ascii=False))
    return '\n'.join(parts)


@pytest.mark.parametrize('lang', ['en', 'es'])
@pytest.mark.parametrize('frequency', ['Annual', 'Monthly'])
def test_complete_runtime_in_both_languages(lang, frequency):
    app = new_app(lang)
    app.session_state['frequency'] = frequency
    app.session_state['compare_countries'] = ['Peru','Brazil','Chile']
    app.run()
    assert not app.exception and not app.error
    assert [tab.label for tab in app.tabs] == [t('section.'+key,lang) for key in ('explore','compare','methodology')]
    assert app.selectbox(key='language').options == ['English','Español']
    assert app.metric[0].label == t('metric.trend', lang)
    assert app.metric[0].value == '+0.370 ' + t('unit.trend',lang)
    assert any(t('methodology.technical',lang) == element.label for element in app.expander)
    assert any(t('column.boundary',lang) in frame.value for frame in app.dataframe)
    text = public_text(app)
    assert t('map.scope',lang) in text
    assert t('map.attribution',lang) in text
    assert t('app.footer',lang) in text
    assert t('methodology.about_text',lang).strip() in text
    assert not any(word in text for word in ('user_confirmed','pending_confirmation','/private/'))
    if lang == 'es':
        for key, english in catalogs()['en'].items():
            if len(english.strip()) > 24 and english != catalogs()['es'][key] and not placeholders(english):
                assert english.strip() not in text, key
        assert 'Unavailable' not in text
        assert 'Annual average' not in text
        assert 'Monthly average' not in text
        assert 'Country to explore' not in text
        assert 'Confidence interval' not in text
        assert 'Tendencia' in text and 'Perú' in text


@pytest.mark.parametrize('active', ['Explore', 'Compare', 'Methodology'])
def test_language_switch_preserves_all_context_and_reuses_science(active):
    app = new_app().run()
    app.selectbox(key='country').set_value('Brazil')
    app.multiselect(key='compare_countries').set_value(['Peru','Brazil'])
    app.selectbox(key='start_year').set_value(2010)
    app.selectbox(key='end_year').set_value(2020)
    # A real browser changes this enabled toggle before switching to Monthly,
    # where it is disabled. Do not submit both changes as one forged event.
    app.toggle(key='show_trend').set_value(False).run()
    app.radio(key='frequency').set_value('Monthly')
    app.session_state['active_tab'] = active
    app.run()
    metrics = [m.value for m in app.metric]
    cache = app.session_state['_analysis_cache']
    results = {key: entry[1] for key,entry in cache.items()}
    # Raising here proves switching does not even call the loaders or regressions.
    with patch('core.region_data.load_country', side_effect=AssertionError('dataset reloaded')), \
         patch('core.country_comparison.prepare_comparison', side_effect=AssertionError('comparison recalculated')), \
         patch('core.map_data.load_map_data', side_effect=AssertionError('map recalculated')), \
         patch('core.dashboard_data.prepare_period', side_effect=AssertionError('period recalculated')):
        app.selectbox(key='language').set_value('es').run()
    assert not app.exception and not app.error
    assert app.selectbox(key='country').value == 'Brazil'
    assert app.multiselect(key='compare_countries').value == ['Peru','Brazil']
    assert app.selectbox(key='start_year').value == 2010
    assert app.selectbox(key='end_year').value == 2020
    assert app.radio(key='frequency').value == 'Monthly'
    assert app.toggle(key='show_trend').value is False
    assert app.toggle(key='show_trend').disabled
    assert app.session_state['analysis_section'] == active.lower()
    assert app.session_state['active_tab'] == t('section.'+active.lower(),'es')
    assert [m.value.replace('°C/década','°C/decade').replace(' a ',' to ') for m in app.metric] == metrics
    assert all(app.session_state['_analysis_cache'][key][1] is value for key,value in results.items())
    app.selectbox(key='language').set_value('en').run()
    assert not app.exception and not app.error
    assert app.selectbox(key='country').value == 'Brazil'
    assert app.session_state['active_tab'] == active
    assert [m.value for m in app.metric] == metrics


def test_simultaneous_date_change_and_language_switch_recalculates_required_values():
    app = new_app().run()
    with patch('core.dashboard_data.prepare_period', wraps=prepare_period) as prepare:
        app.selectbox(key='language').set_value('es')
        app.selectbox(key='start_year').set_value(2010).run()
    assert not app.exception and not app.error
    assert prepare.call_count > 0
    assert app.metric[-1].value == '16'
    assert app.session_state['_analysis_cache']['explore'][1].trend.years[0] == 2010


def test_source_metadata_signature_tracks_changed_and_missing_inputs(tmp_path):
    (tmp_path / 'data/raw').mkdir(parents=True)
    source = tmp_path / 'data/raw/source.csv'
    source.write_text('one')
    first = source_signature(tmp_path)
    source.write_text('two changes')
    second = source_signature(tmp_path)
    assert first != second
    source.unlink()
    assert second != source_signature(tmp_path)


def test_changed_source_signature_prevents_stale_language_switch_reuse():
    app = new_app().run()
    with patch('core.dashboard_state.source_signature', return_value=(('changed', 1, 1),)), \
         patch('core.region_data.load_country', wraps=load_country) as loader, \
         patch('core.dashboard_data.prepare_period', wraps=prepare_period) as prepare:
        app.selectbox(key='language').set_value('es').run()
    assert not app.exception and not app.error
    assert loader.call_count > 0
    assert prepare.call_count > 0


def test_urls_identifiers_and_numerical_conventions_are_preserved():
    for key in ('methodology.links', 'map.attribution'):
        assert re.findall(r'https?://[^)\s]+', t(key)) == re.findall(r'https?://[^)\s]+', t(key, 'es'))
    for lang in ('en', 'es'):
        technical = t('methodology.technical_text', lang)
        for unchanged in ('M2TMNXSLV', 'v5.12.4', 'T2M', '0.5° × 0.625°',
                          '°C = K − 273.15', 'n/(n−2)', 'floor(4 × (n/100)^(2/9))', 'Student-t', 'OLS', 'HAC'):
            assert unchanged in technical
        assert '+0.123' in t('common.interval', lang, low=.123, high=.456)


@pytest.mark.parametrize('lang', ['en','es'])
def test_short_invalid_and_empty_comparison_runtime(lang):
    app = new_app(lang).run()
    assert any(element.value == t('compare.empty',lang) for element in app.info)
    app.selectbox(key='start_year').set_value(2025)
    app.multiselect(key='compare_countries').set_value(['Peru','Brazil'])
    app.run()
    assert not app.exception and not app.error
    assert not app.metric
    assert any(element.value == t('notice.insufficient',lang) for element in app.info)
    assert any(element.value == t('compare.insufficient',lang) for element in app.info)
    assert any(t('common.short_period',lang) == element.value for element in app.warning)
    assert any(t('column.trend',lang) in frame.value for frame in app.dataframe)
    if lang == 'es':
        assert 'Unavailable' not in public_text(app)
    app.selectbox(key='end_year').set_value(2024).run()
    assert not app.exception
    assert any(element.value == t('error.period',lang) for element in app.warning)


@pytest.mark.parametrize('lang', ['en','es'])
@pytest.mark.parametrize('target,key', [
    ('core.country_comparison.available_countries','error.registry'),
    ('core.region_data.load_country','error.country'),
    ('core.country_comparison.prepare_comparison','error.comparison'),
    ('core.map_data.load_boundaries','map.error'),
])
def test_localized_errors_hide_internal_details(lang, target, key):
    app = new_app(lang)
    app.session_state['compare_countries'] = ['Peru','Brazil']
    with patch(target, side_effect=ValueError('/private/source.csv checksum user_confirmed')):
        app.run()
    assert not app.exception
    expected = t(key,lang,country=country_name('Peru',lang)) if key=='error.country' else t(key,lang)
    assert expected in [element.value for element in [*app.info,*app.error]]
    assert '/private/' not in public_text(app)


def test_language_is_scoped_to_each_session():
    spanish = new_app('es').run()
    english = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert not spanish.exception and not english.exception
    assert spanish.selectbox(key='language').value == 'es'
    assert english.selectbox(key='language').value == 'en'
    assert spanish.metric[0].label == 'Tendencia de temperatura'
    assert english.metric[0].label == 'Temperature trend'
