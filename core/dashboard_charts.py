"""Plotly presentation only; trend coefficients are supplied by core inference."""

import plotly.graph_objects as go

from core.dashboard_data import DashboardPeriod, annual_chart_data
from core.i18n import t, country_name, month_labels
from core.region_data import COUNTRIES


def series_name(name: str, lang: str) -> str:
    """Keep arbitrary synthetic series labels supported by the chart helpers."""
    return country_name(name, lang) if name in COUNTRIES else name


def temperature_figure(period: DashboardPeriod, frequency: str, show_trend: bool = True,
                       *, color: str = "#007F86", lang: str = "en") -> go.Figure:
    """Monthly values retain seasonality; annual regression is never plotted as monthly."""
    if frequency not in ("Annual", "Monthly"):
        raise ValueError("Frequency must be Annual or Monthly.")
    figure = go.Figure()
    if frequency == "Annual":
        annual = annual_chart_data(period)
        figure.add_trace(go.Scatter(
            x=annual.year.tolist(), y=annual.temperature_c.tolist(),
            name=t("chart.annual", lang), mode="lines+markers",
            line=dict(color=color, width=3), marker=dict(size=8),
            customdata=[[int(row.valid_months), t("common.yes" if row.is_complete else "common.no", lang)]
                        for row in period.annual.itertuples()],
            hovertemplate=t("chart.annual_hover", lang),
            connectgaps=False,
        ))
        if show_trend and period.trend is not None:
            figure.add_trace(go.Scatter(
                x=list(period.trend.years), y=list(period.trend.fitted_values),
                mode="lines", name=t("chart.linear", lang),
                line=dict(color="#C05B26", width=3, dash="dash"),
                hovertemplate=t("chart.linear_hover", lang),
            ))
        figure.update_xaxes(title_text=t("chart.year", lang), tickformat="d", dtick=max(1, len(period.annual) // 8))
    else:
        figure.add_trace(go.Scatter(
            x=period.monthly.date.tolist(), y=period.monthly.temperature_c.tolist(),
            name=t("chart.monthly", lang), mode="lines+markers",
            line=dict(color=color, width=2), marker=dict(size=4), connectgaps=False,
            customdata=[[label] for label in month_labels(period.monthly.date, lang)],
            hovertemplate=t("chart.monthly_hover", lang),
        ))
        figure.update_xaxes(title_text=t("chart.month", lang), tickformat="%b %Y", rangeslider_visible=True)
        localized_month_ticks(figure, period.monthly.date, lang)
    figure.update_layout(
        template="plotly_white", height=470, autosize=True,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", color="#142C40", size=13),
        margin=dict(l=12, r=12, t=15, b=30), hovermode="x unified",
        uirevision=plot_revision({'explore': period}, frequency),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis=dict(title=t("chart.temperature_axis", lang), gridcolor="#DCE6EC", zeroline=False),
    )
    return figure


def comparison_temperature_figure(periods: dict[str, DashboardPeriod], frequency: str,
                                  colors: dict[str, str], *, lang: str = "en") -> go.Figure:
    """Plot actual processed values; NaNs break lines rather than being interpolated."""
    if frequency not in ("Annual", "Monthly"):
        raise ValueError("Frequency must be Annual or Monthly.")
    figure = go.Figure()
    for country, period in periods.items():
        table = annual_chart_data(period) if frequency == "Annual" else period.monthly
        x = table.year.tolist() if frequency == "Annual" else table.date.tolist()
        date_format = "%{x:.0f}" if frequency == "Annual" else "%{customdata[0]}"
        figure.add_trace(go.Scatter(
            x=x, y=table.temperature_c.tolist(), name=series_name(country, lang),
            mode="lines+markers", connectgaps=False,
            line=dict(color=colors[country], width=2),
            marker=dict(size=6 if frequency == "Annual" else 3),
            customdata=None if frequency == "Annual" else [[label] for label in month_labels(table.date, lang)],
            hovertemplate=date_format + "<br>%{y:.3f} °C<extra>" + series_name(country, lang) + "</extra>",
        ))
    figure.update_layout(template="plotly_white", height=470, hovermode="x unified",
                          uirevision=plot_revision(periods, frequency),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=12, r=12, t=20, b=30),
                          legend=dict(orientation="h", y=1.02),
                          yaxis_title=t("chart.temperature_axis", lang))
    figure.update_xaxes(title_text=t("chart.year", lang) if frequency == "Annual" else t("chart.month", lang),
                        tickformat="d" if frequency == "Annual" else "%b %Y")
    if frequency == "Monthly":
        figure.update_xaxes(rangeslider_visible=True)
        dates = sorted({date for period in periods.values() for date in period.monthly.date})
        localized_month_ticks(figure, dates, lang)
    return figure


def warming_rate_figure(periods: dict[str, DashboardPeriod], colors: dict[str, str], *, lang: str = "en") -> go.Figure:
    """Same OLS slopes, with HAC uncertainty; markers describe individual tests."""
    figure = go.Figure()
    for country, period in periods.items():
        result = period.trend
        if result is None:
            continue
        interval = result.hac.confidence_interval_per_decade
        significant = result.hac.significant
        indicator = "*" if significant is True else t("common.not_significant", lang) if significant is False else t("common.not_assessed", lang)
        significance_label = t("common.significant", lang) if significant is True else t("common.nonsignificant", lang) if significant is False else t("common.not_assessed", lang)
        p_value = f"{result.hac.p_value:.6g}" if result.hac.p_value is not None else t("common.unavailable", lang)
        ci_label = f"[{interval[0]:+.6f}, {interval[1]:+.6f}]" if interval else t("common.unavailable", lang)
        error = (dict(type="data", symmetric=False, array=[interval[1] - result.slope_per_decade],
                      arrayminus=[result.slope_per_decade - interval[0]], color="#142C40", thickness=1.5)
                 if interval else None)
        figure.add_trace(go.Bar(
            x=[result.slope_per_decade], y=[series_name(country, lang)], orientation="h", name=series_name(country, lang),
            marker_color=colors[country], error_x=error,
            text=[indicator], textposition="outside", cliponaxis=False,
            customdata=[[ci_label, p_value, f"{result.years[0]}–{result.years[-1]}", significance_label]],
            hovertemplate=t("chart.rate_hover", lang, country=series_name(country, lang)),
        ))
    figure.add_vline(x=0, line_color="#576D7D", line_dash="dash", line_width=1)
    figure.update_layout(template="plotly_white", showlegend=False, height=350,
                          uirevision=plot_revision(periods, 'Annual'),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=12, r=35, t=15, b=40),
                          xaxis_title=t("chart.trend_axis", lang),
                          yaxis=dict(autorange="reversed", categoryorder="array", categoryarray=[series_name(country, lang) for country in periods]))
    return figure


def localized_month_ticks(figure: go.Figure, dates, lang: str) -> None:
    """Keep datetime coordinates and interactions; localize only displayed labels."""
    dates = list(dates)
    step = max(1, len(dates) // 8)
    ticks = dates[::step]
    figure.update_xaxes(hoverformat="%Y-%m", tickmode="array", tickvals=ticks,
                        ticktext=month_labels(ticks, lang, abbreviated=True))


def plot_revision(periods: dict[str, DashboardPeriod], frequency: str) -> str:
    """Stable across translations; new scientific selections reset the viewport."""
    context = []
    for name, period in periods.items():
        countries = tuple(period.monthly.country.unique()) if 'country' in period.monthly else ()
        context.append((name, countries, str(period.monthly.date.min()), str(period.monthly.date.max())))
    return repr((frequency, context))
