"""
Florence-themed Plotly chart builders.

Each function takes the data + optional config and returns a plotly Figure
ready to st.plotly_chart().
"""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd

from . import (
    FLORENCE_TEAL, FLORENCE_TEAL_DARK, FLORENCE_NAVY, FLORENCE_GRAY,
    FLORENCE_BORDER, FLORENCE_MUTED, TEAL_SCALE, DIVERGING,
)


def _apply_florence_layout(fig: go.Figure, *, title: str = "", height: int = 420) -> go.Figure:
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(family="Newsreader, Georgia, serif", size=20, color=FLORENCE_NAVY),
            x=0, xanchor="left",
        ),
        font=dict(family="Inter, sans-serif", color=FLORENCE_NAVY, size=12),
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=20, r=20, t=70, b=40),
        height=height,
        hoverlabel=dict(font=dict(family="Inter, sans-serif", size=11)),
    )
    return fig


def state_choropleth(
    state_values: dict[str, float],
    *,
    title: str = "",
    colorbar_title: str = "",
    value_format: str = "$,.2f",
    height: int = 480,
) -> go.Figure:
    """U.S. state-level choropleth, e.g. RN wages by state."""
    df = pd.DataFrame({
        "state": list(state_values.keys()),
        "value": list(state_values.values()),
    })
    fig = go.Figure(
        data=go.Choropleth(
            locations=df["state"],
            locationmode="USA-states",
            z=df["value"],
            colorscale=TEAL_SCALE,
            colorbar=dict(
                title=dict(text=colorbar_title,
                           font=dict(family="Inter, sans-serif", size=11, color=FLORENCE_MUTED)),
                thickness=12, len=0.7,
            ),
            marker_line_color="white",
            marker_line_width=1,
            hovertemplate="<b>%{location}</b><br>%{z:" + value_format + "}<extra></extra>",
        )
    )
    fig.update_layout(
        geo=dict(scope="usa", showlakes=False, landcolor=FLORENCE_GRAY, bgcolor="white"),
    )
    return _apply_florence_layout(fig, title=title, height=height)


def time_series(
    df: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    color_col: str | None = None,
    title: str = "",
    y_label: str = "",
    height: int = 380,
) -> go.Figure:
    """Single or multi-series time series. df rows ordered by x_col."""
    if color_col is None:
        fig = go.Figure(
            data=go.Scatter(
                x=df[x_col], y=df[y_col],
                mode="lines+markers",
                line=dict(color=FLORENCE_TEAL_DARK, width=2.5),
                marker=dict(size=5, color=FLORENCE_TEAL),
                hovertemplate=f"%{{x}}<br>%{{y:,.2f}}<extra></extra>",
            )
        )
    else:
        # Multiple series — assign colors
        palette = [FLORENCE_TEAL_DARK, FLORENCE_NAVY, "#FF8C42", "#7B68EE", "#E94B6E"]
        fig = go.Figure()
        for i, (key, sub) in enumerate(df.groupby(color_col)):
            fig.add_trace(go.Scatter(
                x=sub[x_col], y=sub[y_col],
                mode="lines+markers",
                name=str(key),
                line=dict(color=palette[i % len(palette)], width=2.2),
                marker=dict(size=4),
                hovertemplate=f"<b>{key}</b><br>%{{x}}<br>%{{y:,.2f}}<extra></extra>",
            ))
    fig.update_xaxes(
        showgrid=False, color=FLORENCE_MUTED,
        tickfont=dict(family="Inter, sans-serif", size=10),
    )
    fig.update_yaxes(
        title=dict(text=y_label,
                   font=dict(family="Inter, sans-serif", size=11, color=FLORENCE_MUTED)),
        gridcolor=FLORENCE_BORDER, color=FLORENCE_MUTED, zeroline=False,
        tickfont=dict(family="Inter, sans-serif", size=10),
    )
    return _apply_florence_layout(fig, title=title, height=height)


def bar_horizontal(
    df: pd.DataFrame,
    *,
    label_col: str,
    value_col: str,
    title: str = "",
    x_label: str = "",
    color_col: str | None = None,
    height: int = 420,
) -> go.Figure:
    """Horizontal bar chart — top N items."""
    df = df.sort_values(value_col, ascending=True)
    colors = (
        [FLORENCE_TEAL_DARK] * len(df)
        if color_col is None
        else df[color_col].tolist()
    )
    fig = go.Figure(
        data=go.Bar(
            x=df[value_col],
            y=df[label_col],
            orientation="h",
            marker=dict(color=colors),
            hovertemplate="<b>%{y}</b><br>%{x:,.2f}<extra></extra>",
        )
    )
    fig.update_xaxes(
        title=dict(text=x_label,
                   font=dict(family="Inter, sans-serif", size=11, color=FLORENCE_MUTED)),
        gridcolor=FLORENCE_BORDER, color=FLORENCE_MUTED,
        tickfont=dict(family="Inter, sans-serif", size=10),
    )
    fig.update_yaxes(
        showgrid=False, color=FLORENCE_NAVY,
        tickfont=dict(family="Inter, sans-serif", size=11),
    )
    return _apply_florence_layout(fig, title=title, height=height)


def delta_bar(
    df: pd.DataFrame,
    *,
    label_col: str,
    delta_col: str,
    title: str = "",
    x_label: str = "% change",
    height: int = 420,
) -> go.Figure:
    """Horizontal diverging bar (red = down, teal = up)."""
    df = df.sort_values(delta_col)
    colors = ["#D14343" if v < 0 else FLORENCE_TEAL_DARK for v in df[delta_col]]
    fig = go.Figure(
        data=go.Bar(
            x=df[delta_col], y=df[label_col],
            orientation="h",
            marker=dict(color=colors),
            hovertemplate="<b>%{y}</b><br>%{x:+,.2f}%<extra></extra>",
        )
    )
    fig.update_xaxes(
        title=dict(text=x_label,
                   font=dict(family="Inter, sans-serif", size=11, color=FLORENCE_MUTED)),
        gridcolor=FLORENCE_BORDER, color=FLORENCE_MUTED,
        zeroline=True, zerolinecolor=FLORENCE_NAVY, zerolinewidth=1.5,
        tickfont=dict(family="Inter, sans-serif", size=10),
        ticksuffix="%",
    )
    fig.update_yaxes(
        showgrid=False, color=FLORENCE_NAVY,
        tickfont=dict(family="Inter, sans-serif", size=11),
    )
    return _apply_florence_layout(fig, title=title, height=height)


def stat_card_data(label: str, value: str, delta_pct: float | None = None,
                   interpretation: str = "") -> dict:
    """Return a dict for Streamlit rendering of a single stat card."""
    return dict(label=label, value=value, delta_pct=delta_pct, interpretation=interpretation)
