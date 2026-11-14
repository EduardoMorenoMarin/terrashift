"""Session-local presentation reuse and language-independent analysis context."""

from pathlib import Path

import streamlit as st

from core.i18n import LANGUAGES, t


def source_signature(root: Path) -> tuple:
    """Metadata only: a language change never reads NASA file contents."""
    paths = [root / 'metadata/country_mapping.json',
             root / 'data/geography/south_america.geojson', *sorted((root / 'data/raw').glob('*.csv'))]
    signature = []
    for path in paths:
        try:
            stat = path.stat()
            signature.append((str(path), stat.st_size, stat.st_mtime_ns))
        except OSError:
            signature.append((str(path), None, None))
    return tuple(signature)


def begin_presentation(lang: str, root: Path) -> None:
    signature = source_signature(root)
    previous = st.session_state.get('_presentation_context')
    st.session_state['_reuse_analysis'] = previous is not None and previous != (lang, signature) and previous[1] == signature
    st.session_state['_presentation_context'] = (lang, signature)


def analysis_value(slot: str, context: tuple, build):
    """Reuse successful scientific outputs on language-only reruns.

    Other reruns retain the original refresh behavior; failures are not cached.
    Context changes or changed source metadata always refresh. Values are scoped
    to one browser session and never mixed between users or languages.
    """
    cache = st.session_state.setdefault('_analysis_cache', {})
    signature = (st.session_state['_presentation_context'][1], context)
    if st.session_state.get('_reuse_analysis') and slot in cache and cache[slot][0] == signature:
        return cache[slot][1]
    cache.pop(slot, None)
    value = build()
    cache[slot] = (signature, value)
    return value


def localized_tabs(lang: str):
    sections = ('explore', 'compare', 'methodology')
    canonical = {t('section.' + section, language): section for language in LANGUAGES for section in sections}
    active = canonical.get(st.session_state.get('active_tab'), st.session_state.get('analysis_section', 'explore'))
    st.session_state['analysis_section'] = active
    label = t('section.' + active, lang)
    # Remap the widget's localized label before constructing it, preserving context.
    if st.session_state.get('active_tab') != label:
        st.session_state['active_tab'] = label
    return st.tabs([t('section.' + section, lang) for section in sections],
                   key='active_tab', on_change='rerun')
