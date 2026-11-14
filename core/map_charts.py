"""Plotly map presentation; supplied values come from the annual trend pipeline."""

import pandas as pd
import plotly.graph_objects as go

from core.i18n import t, country_name
from core.dashboard_copy import localize_notice


def country_trend_figure(table: pd.DataFrame, geojson: dict, selected_iso3: str, *, lang: str = "en") -> go.Figure:
    """Tile-free map with bundled boundaries, symmetric scale and missing-data fill."""
    figure = go.Figure()
    valid = table['Trend (°C/decade)'].notna()
    extent = float(table.loc[valid, 'Trend (°C/decade)'].abs().max()) if valid.any() else 0
    extent = extent or 1.0  # A display range only, including for constant zero trends.
    for available in (False, True):
        rows = table.loc[valid if available else ~valid]
        if rows.empty:
            continue
        custom = [[country_name(row['Country'], lang), row['Selected period'],
                   row['Analysis period'] if available else t('common.unavailable', lang),
                   f"{row['Trend (°C/decade)']:+.3f} {t('unit.trend', lang)}" if available else t('common.unavailable', lang),
                   localize_notice(row['Notice'], lang)] for _, row in rows.iterrows()]
        figure.add_trace(go.Choroplethmap(
            geojson=geojson, featureidkey='properties.iso3', locations=rows['ISO-3'].tolist(),
            z=rows['Trend (°C/decade)'].tolist() if available else [0] * len(rows),
            zmin=-extent, zmax=extent, zmid=0,
            colorscale='RdBu_r' if available else [[0, '#DCE2E7'], [1, '#DCE2E7']],
            showscale=available,
            colorbar=dict(title=dict(text=t('map.colorbar', lang)), thickness=16, len=.7),
            marker=dict(line=dict(
                color=['#142C40' if code == selected_iso3 else 'white' for code in rows['ISO-3']],
                width=[3 if code == selected_iso3 else 1 for code in rows['ISO-3']])),
            customdata=custom, name=t('map.traces' if available else 'map.trace_missing', lang),
            hovertemplate=t('map.hover', lang),
        ))
    figure.update_layout(
        map=dict(style='white-bg', center=dict(lat=-23, lon=-60), zoom=1.65),
        template='plotly_white', height=540, autosize=True,
        margin=dict(l=0, r=0, t=5, b=0), paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family='Arial, sans-serif', color='#142C40', size=13),
        showlegend=False, uirevision='south-america',
    )
    return figure
