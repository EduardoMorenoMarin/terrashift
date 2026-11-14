"""Plotly presentation only; trend coefficients are supplied by core inference."""

import plotly.graph_objects as go

from core.dashboard_data import DashboardPeriod


def temperature_figure(period: DashboardPeriod, frequency: str, show_trend: bool = True,
                       *, color: str = "#007F86") -> go.Figure:
    """Monthly values retain seasonality; annual regression is never plotted as monthly."""
    if frequency not in ("Annual", "Monthly"):
        raise ValueError("Frequency must be Annual or Monthly.")
    figure = go.Figure()
    if frequency == "Annual":
        figure.add_trace(go.Scatter(
            x=period.annual.year.tolist(), y=period.annual.temperature_c.tolist(),
            name="Annual average", mode="lines+markers",
            line=dict(color=color, width=3), marker=dict(size=8),
            customdata=[[int(row.valid_months), "Yes" if row.is_complete else "No"]
                        for row in period.annual.itertuples()],
            hovertemplate="%{x:.0f}<br>%{y:.3f} °C<br>Months available: %{customdata[0]}<br>Full year: %{customdata[1]}<extra>Annual average</extra>",
            connectgaps=False,
        ))
        if show_trend and period.trend is not None:
            figure.add_trace(go.Scatter(
                x=list(period.trend.years), y=list(period.trend.fitted_values),
                mode="lines", name="Linear trend",
                line=dict(color="#C05B26", width=3, dash="dash"),
                hovertemplate="%{x:.0f}<br>Trend estimate: %{y:.3f} °C<extra>Linear trend</extra>",
            ))
        figure.update_xaxes(title_text="Year", tickformat="d", dtick=max(1, len(period.annual) // 8))
    else:
        figure.add_trace(go.Scatter(
            x=period.monthly.date.tolist(), y=period.monthly.temperature_c.tolist(),
            name="Monthly average", mode="lines+markers",
            line=dict(color=color, width=2), marker=dict(size=4), connectgaps=False,
            hovertemplate="%{x|%B %Y}<br>%{y:.3f} °C<extra>Monthly average</extra>",
        ))
        figure.update_xaxes(title_text="Month", tickformat="%b %Y", rangeslider_visible=True)
    figure.update_layout(
        template="plotly_white", height=470, autosize=True,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", color="#142C40", size=13),
        margin=dict(l=12, r=12, t=15, b=30), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis=dict(title="Air temperature (°C)", gridcolor="#DCE6EC", zeroline=False),
    )
    return figure


def comparison_temperature_figure(periods: dict[str, DashboardPeriod], frequency: str,
                                  colors: dict[str, str]) -> go.Figure:
    """Plot actual processed values; NaNs break lines rather than being interpolated."""
    if frequency not in ("Annual", "Monthly"):
        raise ValueError("Frequency must be Annual or Monthly.")
    figure = go.Figure()
    for country, period in periods.items():
        table = period.annual if frequency == "Annual" else period.monthly
        x = table.year.tolist() if frequency == "Annual" else table.date.tolist()
        date_format = "%{x:.0f}" if frequency == "Annual" else "%{x|%B %Y}"
        figure.add_trace(go.Scatter(
            x=x, y=table.temperature_c.tolist(), name=country,
            mode="lines+markers", connectgaps=False,
            line=dict(color=colors[country], width=2),
            marker=dict(size=6 if frequency == "Annual" else 3),
            hovertemplate=date_format + "<br>%{y:.3f} °C<extra>" + country + "</extra>",
        ))
    figure.update_layout(template="plotly_white", height=470, hovermode="x unified",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=12, r=12, t=20, b=30),
                          legend=dict(orientation="h", y=1.02),
                          yaxis_title="Air temperature (°C)")
    figure.update_xaxes(title_text="Year" if frequency == "Annual" else "Month",
                        tickformat="d" if frequency == "Annual" else "%b %Y")
    if frequency == "Monthly":
        figure.update_xaxes(rangeslider_visible=True)
    return figure


def warming_rate_figure(periods: dict[str, DashboardPeriod], colors: dict[str, str]) -> go.Figure:
    """Same OLS slopes, with HAC uncertainty; markers describe individual tests."""
    figure = go.Figure()
    for country, period in periods.items():
        result = period.trend
        if result is None:
            continue
        interval = result.hac.confidence_interval_per_decade
        significant = result.hac.significant
        indicator = "*" if significant is True else "Not significant" if significant is False else "Not assessed"
        significance_label = "Statistically significant" if significant is True else "Not statistically significant" if significant is False else "Not assessed"
        p_value = f"{result.hac.p_value:.6g}" if result.hac.p_value is not None else "Unavailable"
        ci_label = f"[{interval[0]:+.6f}, {interval[1]:+.6f}]" if interval else "Unavailable"
        error = (dict(type="data", symmetric=False, array=[interval[1] - result.slope_per_decade],
                      arrayminus=[result.slope_per_decade - interval[0]], color="#142C40", thickness=1.5)
                 if interval else None)
        figure.add_trace(go.Bar(
            x=[result.slope_per_decade], y=[country], orientation="h", name=country,
            marker_color=colors[country], error_x=error,
            text=[indicator], textposition="outside", cliponaxis=False,
            customdata=[[ci_label, p_value, f"{result.years[0]}–{result.years[-1]}", significance_label]],
            hovertemplate=(country + "<br>Trend: %{x:+.6f} °C/decade<br>95% confidence interval: %{customdata[0]} °C/decade"
                           "<br>Trend p-value: %{customdata[1]}<br>Period: %{customdata[2]}"
                           "<br>Trend significance: %{customdata[3]}<extra></extra>"),
        ))
    figure.add_vline(x=0, line_color="#576D7D", line_dash="dash", line_width=1)
    figure.update_layout(template="plotly_white", showlegend=False, height=350,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=12, r=35, t=15, b=40),
                          xaxis_title="Temperature trend (°C/decade)",
                          yaxis=dict(autorange="reversed", categoryorder="array", categoryarray=list(periods)))
    return figure
