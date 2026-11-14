"""Strict, dependency-free translations. Language is explicit, never process-global."""

import json
from functools import lru_cache
from pathlib import Path
from string import Formatter

LOCALES = Path(__file__).resolve().parents[1] / 'locales'
LANGUAGES = {'en': 'English', 'es': 'Español'}


class TranslationError(ValueError):
    """Missing/invalid translations or incompatible interpolation arguments."""


def placeholders(template: str) -> dict[str, tuple[str, str | None]]:
    """Named fields only; format specifications must also match between locales."""
    fields = {}
    try:
        for _, name, spec, conversion in Formatter().parse(template):
            if name is not None:
                if not name.isidentifier() or '{' in spec or '}' in spec:
                    raise TranslationError(f'Invalid translation placeholder: {name!r}')
                signature = (spec, conversion)
                if name in fields and fields[name] != signature:
                    raise TranslationError(f'Inconsistent format for {name!r}')
                fields[name] = signature
    except ValueError as exc:
        raise TranslationError(f'Invalid translation template: {template!r}') from exc
    return fields


def validate_catalogs(catalogs: dict[str, dict[str, str]]) -> None:
    if set(catalogs) != set(LANGUAGES):
        raise TranslationError('Expected en and es catalogs.')
    if any(not isinstance(catalog, dict) for catalog in catalogs.values()):
        raise TranslationError('Translation catalogs must be JSON objects.')
    reference = catalogs['en']
    for language, catalog in catalogs.items():
        if set(catalog) != set(reference):
            raise TranslationError(f'{language}: missing/extra translation keys: {set(catalog) ^ set(reference)}')
        for key, value in catalog.items():
            if not isinstance(value, str) or not value.strip():
                raise TranslationError(f'{language}: empty or invalid translation: {key}')
            if placeholders(value) != placeholders(reference[key]):
                raise TranslationError(f'{language}: mismatched placeholders: {key}')


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TranslationError(f'Duplicate translation key: {key}')
        result[key] = value
    return result


@lru_cache(maxsize=1)
def catalogs() -> dict[str, dict[str, str]]:
    result = {language: json.loads((LOCALES / f'{language}.json').read_text(encoding='utf-8'),
                                   object_pairs_hook=_unique_keys) for language in LANGUAGES}
    validate_catalogs(result)
    return result


def t(key: str, lang: str = 'en', **variables) -> str:
    if lang not in LANGUAGES:
        raise TranslationError(f'Unknown language: {lang}')
    try:
        template = catalogs()[lang][key]
    except KeyError as exc:
        raise TranslationError(f'Missing translation key: {key}') from exc
    expected = set(placeholders(template))
    if set(variables) != expected:
        raise TranslationError(f'{key}: expected placeholders {expected}, received {set(variables)}')
    try:
        return template.format(**variables)
    except (ValueError, TypeError) as exc:
        raise TranslationError(f'{key}: invalid interpolation values') from exc


def country_name(country: str, lang: str = 'en') -> str:
    """Canonical registry names stay internal, including in widget option values."""
    return t(f'country.{country}', lang)


def plural(key: str, count: int, lang: str = 'en') -> str:
    """English and Spanish use the singular form for one, plural otherwise."""
    return t(key + ('.one' if count == 1 else '.other'), lang, count=count)


def month_labels(dates, lang: str = 'en', *, abbreviated: bool = False) -> list[str]:
    prefix = 'month_short' if abbreviated else 'month'
    return [f'{t(f"{prefix}.{date.month}", lang)} {date.year}' for date in dates]
