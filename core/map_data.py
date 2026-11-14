"""ISO-3 geographic joins and map values, independent of the dashboard UI."""

import json
import logging
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from core.dashboard_data import prepare_period
from core.data_loader import RAW_DIRECTORY
from core.region_data import COUNTRIES, MAPPING_PATH, load_country, read_country_mapping

BOUNDARIES_PATH = Path(__file__).resolve().parents[1] / 'data/geography/south_america.geojson'
LOGGER = logging.getLogger(__name__)


def validate_map_registry(registry: dict[str, dict]) -> None:
    """Require all 12 registered countries and distinct explicit ISO-3 keys."""
    if set(registry) != set(COUNTRIES):
        raise ValueError('The map requires all 12 South American countries.')
    codes = [entry.get('iso3') for entry in registry.values()]
    if any(not isinstance(code, str) or not re.fullmatch(r'[A-Z]{3}', code) for code in codes):
        raise ValueError('Each map country needs an explicit ISO-3 code.')
    if len(set(codes)) != 12:
        raise ValueError('Map ISO-3 codes must be unique.')


def validate_geographic_join(geojson: dict, registry: dict[str, dict]) -> None:
    """Reject missing, duplicate or extra features before rendering any values."""
    validate_map_registry(registry)
    if geojson.get('type') != 'FeatureCollection' or not isinstance(geojson.get('features'), list):
        raise ValueError('Expected a geographic FeatureCollection.')
    codes = []
    for feature in geojson['features']:
        code = feature.get('properties', {}).get('iso3')
        geometry = feature.get('geometry') or {}
        if (feature.get('type') != 'Feature' or not isinstance(code, str)
                or geometry.get('type') not in ('Polygon', 'MultiPolygon') or not geometry.get('coordinates')):
            raise ValueError('Each geographic feature needs an ISO-3 key and polygon geometry.')
        codes.append(code)
    expected = {entry['iso3'] for entry in registry.values()}
    if set(codes) != expected or any(count != 1 for count in Counter(codes).values()):
        raise ValueError('All 12 countries must match geographic features exactly once by ISO-3.')


def load_boundaries(registry: dict[str, dict], path: str | Path = BOUNDARIES_PATH) -> dict:
    geojson = json.loads(Path(path).read_text(encoding='utf-8'))
    validate_geographic_join(geojson, registry)
    return geojson


def map_trend_table(monthly_by_country: dict[str, pd.DataFrame], registry: dict[str, dict],
                    start_year: int, end_year: int) -> pd.DataFrame:
    """Use the existing annual pipeline; absent data stays unavailable, never zero.

    Selected period and actual fitted period are separate so incomplete endpoints
    cannot mislabel a trend. Source frames are never modified.
    """
    validate_map_registry(registry)
    # Validate the range even when every source is unavailable.
    prepare_period(pd.DataFrame({'date': pd.Series(dtype='datetime64[ns]')}), start_year, end_year)
    rows = []
    for country, entry in registry.items():
        monthly = monthly_by_country.get(country)
        period = prepare_period(monthly, start_year, end_year) if monthly is not None else None
        trend = period.trend if period is not None else None
        rows.append({
            'Country': country, 'ISO-3': entry['iso3'],
            'Selected period': f'{start_year}–{end_year}',
            'Analysis period': f'{trend.years[0]}–{trend.years[-1]}' if trend else 'Unavailable',
            'Years analyzed': len(period.complete_annual) if period is not None else 0,
            'Trend (°C/decade)': trend.slope_per_decade if trend else None,
            'Notice': (period.analysis_notice or '') if period is not None else 'Temperature data is unavailable.',
        })
    return pd.DataFrame(rows)


def load_map_data(start_year: int, end_year: int, *, mapping_path: str | Path = MAPPING_PATH,
                  raw_directory: str | Path = RAW_DIRECTORY,
                  boundaries_path: str | Path = BOUNDARIES_PATH) -> tuple[pd.DataFrame, dict]:
    registry = read_country_mapping(mapping_path)
    geojson = load_boundaries(registry, boundaries_path)
    monthly = {}
    for country in registry:
        try:
            monthly[country] = load_country(country, mapping_path=mapping_path,
                                            raw_directory=raw_directory).monthly
        except (OSError, ValueError):
            LOGGER.exception('Map temperature source unavailable for %s', country)
    return map_trend_table(monthly, registry, start_year, end_year), geojson
