"""Localized public tables and Plotly chrome; canonical data/CSV stay unchanged."""

import pandas as pd

from core.dashboard_data import DashboardPeriod
from core.i18n import catalogs, country_name, t, TranslationError

NOTICE_KEYS = ('notice.no_data', 'notice.insufficient', 'notice.gaps', 'notice.source')
COLUMN_KEYS = ('column.country', 'column.date', 'column.year', 'column.temperature_k',
               'column.temperature_c', 'column.months', 'column.complete', 'column.period',
               'column.selected_period', 'column.years', 'column.trend', 'column.ci',
               'column.p', 'column.r2', 'column.significance', 'column.notice')
STATUS_KEYS = ('common.unavailable', 'common.significant', 'common.nonsignificant',
               'common.not_assessed', 'common.yes', 'common.no')


def localize_notice(notice: str | None, lang: str = 'en') -> str:
    if not notice:
        return ''
    keys = {t(key): key for key in NOTICE_KEYS}
    try:
        return t(keys[notice], lang)
    except KeyError as exc:
        raise TranslationError(f'Unknown analysis notice: {notice}') from exc


def localize_table(table: pd.DataFrame, lang: str = 'en') -> pd.DataFrame:
    """Copy a canonical public table, translating only known presentation fields."""
    result = table.copy(deep=True)
    if 'Country' in result:
        result['Country'] = result['Country'].map(lambda value: country_name(value, lang))
    status = {t(key): t(key, lang) for key in STATUS_KEYS}
    if 'Notice' in result:
        result['Notice'] = result['Notice'].map(lambda value: localize_notice(value, lang))
    for column in ('Analysis period', 'Trend significance', 'Complete year'):
        if column in result:
            result[column] = result[column].map(lambda value: status.get(value, value))
    interval = t('column.ci')
    if interval in result:
        def format_interval(value):
            if value == t('common.unavailable'):
                return t('common.unavailable', lang)
            low, high = value.split(' to ')
            return t('common.interval', lang, low=float(low), high=float(high))
        result[interval] = result[interval].map(format_interval)
    return result.rename(columns={t(key): t(key, lang) for key in COLUMN_KEYS})


def display_temperature_data(period: DashboardPeriod, frequency: str, *, lang: str = 'en') -> pd.DataFrame:
    if frequency not in ('Annual', 'Monthly'):
        raise ValueError('Choose annual or monthly temperatures.')
    table = (period.annual if frequency == 'Annual' else period.monthly).copy()
    if 'is_complete' in table:
        table['is_complete'] = table['is_complete'].map({True: 'Yes', False: 'No'})
    canonical = table.rename(columns={
        'country': 'Country', 'date': 'Date', 'year': 'Year',
        'temperature_k': 'Temperature (K)', 'temperature_c': 'Temperature (°C)',
        'valid_months': 'Months available', 'is_complete': 'Complete year',
    })
    return localize_table(canonical, lang)


def chart_config(lang: str = 'en', **overrides) -> dict:
    dictionary = {t(key): t(key, lang) for key in catalogs()['en'] if key.startswith('plotly.')}
    config = {'displaylogo': False, 'locale': lang,
              'locales': {lang: {'dictionary': dictionary}}}
    config.update(overrides)
    return config
