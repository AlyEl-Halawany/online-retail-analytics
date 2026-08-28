"""
app/dashboard.py
================
Interactive customer analytics dashboard built with Plotly Dash.

Run from project root:
    python app/dashboard.py

Then open: http://127.0.0.1:8050

Four tabs:
  1. Overview       — KPI cards, revenue by segment, customer count by segment
  2. Revenue Trends — historical + forecast line chart, seasonal pattern
  3. Segments & CLV — scatter plot, CLV by segment, top customers table
  4. Cohort         — retention heatmap, average retention curve
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output

# ── Data paths ────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "dashboard_data"

rfm        = pd.read_csv(DATA_DIR / "customers_rfm.csv")
clv        = pd.read_csv(DATA_DIR / "clv_predictions.csv")
forecast   = pd.read_csv(DATA_DIR / "forecast.csv", parse_dates=["date"])
cohort_raw = pd.read_csv(DATA_DIR / "cohort_matrix.csv", index_col=0)

# Merge CLV segment into rfm for easier access
customers = rfm.merge(
    clv[["CustomerID", "predicted_clv_90d"]],
    on="CustomerID", how="left"
)

# ── Colour palette (consistent across all charts) ─────────────────────────────
SEG_COLORS = {
    "Champions":          "#2E86AB",
    "Loyal Customers":    "#A23B72",
    "Potential Loyalists":"#F18F01",
    "Promising":          "#E9C46A",
    "New Customers":      "#2A9D8F",
    "Recent Low Spenders":"#57CC99",
    "At Risk":            "#E84855",
    "At Risk - Low Value":"#F4A261",
    "About to Sleep":     "#CDB4DB",
    "Hibernating":        "#8D99AE",
    "Needs Attention":    "#BFC0C0",
}

BG_COLOR    = "#0F1117"
CARD_COLOR  = "#1A1D27"
ACCENT      = "#2E86AB"
TEXT_COLOR  = "#E8EAF0"
GRID_COLOR  = "#2A2D3E"
FONT_FAMILY = "Inter, Segoe UI, sans-serif"

# ── Pre-compute summary stats ─────────────────────────────────────────────────
seg_summary = (
    customers.groupby("Segment")
    .agg(
        Customers=("CustomerID", "count"),
        TotalRevenue=("Monetary", "sum"),
        AvgRecency=("Recency", "mean"),
        AvgFrequency=("Frequency", "mean"),
        AvgMonetary=("Monetary", "mean"),
        AvgCLV=("predicted_clv_90d", "mean"),
    )
    .reset_index()
    .sort_values("TotalRevenue", ascending=False)
)

total_revenue    = customers["Monetary"].sum()
total_customers  = customers["CustomerID"].nunique()
champion_rev_pct = customers.loc[customers["Segment"]=="Champions","Monetary"].sum() / total_revenue * 100
at_risk_rev      = customers.loc[
    customers["Segment"].isin(["At Risk","At Risk - Low Value"]), "Monetary"
].sum()
avg_clv = customers["predicted_clv_90d"].mean()

# ── Cohort matrix (pivot to long for heatmap) ─────────────────────────────────
cohort_long = cohort_raw.reset_index().melt(
    id_vars=cohort_raw.index.name or "CohortMonth",
    var_name="MonthNumber", value_name="RetentionRate"
)
cohort_long.columns = ["CohortMonth", "MonthNumber", "RetentionRate"]
cohort_long["MonthNumber"] = pd.to_numeric(cohort_long["MonthNumber"], errors="coerce")
cohort_long = cohort_long.dropna(subset=["RetentionRate", "MonthNumber"])
cohort_long = cohort_long[cohort_long["MonthNumber"] <= 13]

avg_retention = cohort_long.groupby("MonthNumber")["RetentionRate"].mean().reset_index()


# ══════════════════════════════════════════════════════════════════════════════
# FIGURE BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def make_segment_donut():
    """Revenue share by segment — donut chart."""
    colors = [SEG_COLORS.get(s, "#BFC0C0") for s in seg_summary["Segment"]]
    fig = go.Figure(go.Pie(
        labels=seg_summary["Segment"],
        values=seg_summary["TotalRevenue"],
        hole=0.55,
        marker_colors=colors,
        textinfo="label+percent",
        textfont_size=11,
        hovertemplate="<b>%{label}</b><br>Revenue: GBP %{value:,.0f}<br>Share: %{percent}<extra></extra>",
    ))
    fig.add_annotation(
        text=f"GBP {total_revenue/1e6:.1f}M",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=18, color=TEXT_COLOR, family=FONT_FAMILY),
    )
    fig.update_layout(**_layout("Revenue by Segment"))
    return fig


def make_customer_bar():
    """Customer count by segment — horizontal bar chart."""
    seg_sorted = seg_summary.sort_values("Customers")
    colors = [SEG_COLORS.get(s, "#BFC0C0") for s in seg_sorted["Segment"]]
    fig = go.Figure(go.Bar(
        x=seg_sorted["Customers"],
        y=seg_sorted["Segment"],
        orientation="h",
        marker_color=colors,
        text=seg_sorted["Customers"].apply(lambda x: f"{x:,}"),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Customers: %{x:,}<extra></extra>",
    ))
    fig.update_layout(**_layout("Customer Count by Segment"))
    fig.update_xaxes(showgrid=True, gridcolor=GRID_COLOR)
    return fig


def make_forecast_chart():
    """Historical + forecast revenue with confidence bands."""
    hist  = forecast[forecast["type"] == "Historical"].copy()
    fcast = forecast[forecast["type"] == "Forecast"].copy()

    fig = go.Figure()

    # Historical area + line
    fig.add_trace(go.Scatter(
        x=hist["date"], y=hist["revenue"] / 1000,
        name="Historical", mode="lines+markers",
        line=dict(color=ACCENT, width=2.5),
        marker=dict(size=4),
        fill="tozeroy", fillcolor=f"rgba(46,134,171,0.1)",
        hovertemplate="<b>%{x|%b %Y}</b><br>Revenue: GBP %{y:,.0f}K<extra></extra>",
    ))

    # Confidence bands (95%)
    fig.add_trace(go.Scatter(
        x=pd.concat([fcast["date"], fcast["date"][::-1]]),
        y=pd.concat([fcast["upper_95"] / 1000, fcast["lower_95"][::-1] / 1000]),
        fill="toself", fillcolor="rgba(232,72,85,0.1)",
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=True, name="95% CI",
        hoverinfo="skip",
    ))

    # Confidence bands (80%)
    fig.add_trace(go.Scatter(
        x=pd.concat([fcast["date"], fcast["date"][::-1]]),
        y=pd.concat([fcast["upper_80"] / 1000, fcast["lower_80"][::-1] / 1000]),
        fill="toself", fillcolor="rgba(232,72,85,0.2)",
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=True, name="80% CI",
        hoverinfo="skip",
    ))

    # Forecast line
    fig.add_trace(go.Scatter(
        x=fcast["date"], y=fcast["forecast_mean"] / 1000,
        name="Forecast", mode="lines+markers",
        line=dict(color="#E84855", width=2.5, dash="dash"),
        marker=dict(size=7, symbol="diamond"),
        hovertemplate="<b>%{x|%b %Y}</b><br>Forecast: GBP %{y:,.0f}K<extra></extra>",
    ))

    # Forecast start line
    if not hist.empty:
        fig.add_vline(
            x=hist["date"].iloc[-1],
            line=dict(color="gray", dash="dot", width=1.5),
            annotation_text="Forecast →",
            annotation_font=dict(color="gray", size=11),
        )

    fig.update_layout(**_layout("Monthly Revenue: Historical & Forecast"))
    fig.update_yaxes(tickprefix="GBP ", ticksuffix="K")
    return fig


def make_seasonal_bar():
    """Average revenue by month of year — shows the seasonal pattern."""
    hist = forecast[forecast["type"] == "Historical"].copy()
    hist["Month"] = hist["date"].dt.month
    hist["MonthName"] = hist["date"].dt.strftime("%b")
    monthly_avg = hist.groupby(["Month", "MonthName"])["revenue"].mean().reset_index().sort_values("Month")

    colors = ["#E84855" if m in [10, 11] else ACCENT for m in monthly_avg["Month"]]

    fig = go.Figure(go.Bar(
        x=monthly_avg["MonthName"],
        y=monthly_avg["revenue"] / 1000,
        marker_color=colors,
        text=(monthly_avg["revenue"] / 1000).apply(lambda x: f"GBP {x:,.0f}K"),
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Avg Revenue: GBP %{y:,.0f}K<extra></extra>",
    ))
    fig.update_layout(**_layout("Average Revenue by Month (Seasonal Pattern)"))
    fig.update_yaxes(tickprefix="GBP ", ticksuffix="K")
    fig.add_annotation(
        text="Peak demand:<br>Oct–Nov",
        x="Nov", y=monthly_avg["revenue"].max() / 1000,
        showarrow=True, arrowhead=2, arrowcolor="#E84855",
        font=dict(color="#E84855", size=11),
        ax=-60, ay=-40,
    )
    return fig


def make_rfm_scatter():
    """Recency vs Frequency scatter, coloured by segment, sized by spend."""
    fig = px.scatter(
        customers,
        x="Recency", y="Frequency",
        color="Segment",
        size="Monetary",
        color_discrete_map=SEG_COLORS,
        hover_data={"CustomerID": True, "Monetary": ":.0f", "Recency": True, "Frequency": True},
        labels={"Recency": "Days Since Last Purchase", "Frequency": "Number of Orders"},
        size_max=25,
    )
    fig.update_traces(marker=dict(opacity=0.7, line=dict(width=0.5, color="white")))
    fig.update_layout(**_layout("Customer Map: Recency vs Frequency"))
    return fig


def make_clv_bar():
    """Average predicted CLV (next 90 days) by segment."""
    seg_clv = (
        customers.groupby("Segment")["predicted_clv_90d"]
        .mean().reset_index()
        .sort_values("predicted_clv_90d")
        .rename(columns={"predicted_clv_90d": "AvgCLV"})
    )
    colors = [SEG_COLORS.get(s, "#BFC0C0") for s in seg_clv["Segment"]]
    fig = go.Figure(go.Bar(
        x=seg_clv["AvgCLV"],
        y=seg_clv["Segment"],
        orientation="h",
        marker_color=colors,
        text=seg_clv["AvgCLV"].apply(lambda x: f"GBP {x:,.0f}"),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Avg CLV (90d): GBP %{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(**_layout("Avg Predicted CLV Next 90 Days by Segment"))
    fig.update_xaxes(tickprefix="GBP ")
    return fig


def make_cohort_heatmap():
    """Cohort retention heatmap."""
    pivot = cohort_long.pivot_table(
        index="CohortMonth", columns="MonthNumber", values="RetentionRate"
    )
    pivot = pivot[[c for c in sorted(pivot.columns) if c <= 13]]

    text_vals = [[
        f"{v:.0f}%" if not np.isnan(v) else ""
        for v in row
    ] for row in pivot.values]

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"Month {int(c)}" for c in pivot.columns],
        y=pivot.index.astype(str),
        text=text_vals,
        texttemplate="%{text}",
        textfont=dict(size=9, color="white"),
        colorscale=[
            [0.0,  "#1A1D27"],
            [0.15, "#1B4F72"],
            [0.40, "#2E86C1"],
            [0.70, "#2E86AB"],
            [1.0,  "#F0E68C"],
        ],
        zmin=0, zmax=100,
        colorbar=dict(
            title="Retention %",
            ticksuffix="%",
            title_font=dict(color=TEXT_COLOR),
            tickfont=dict(color=TEXT_COLOR),
        ),
        hovertemplate="<b>%{y}</b><br>%{x}<br>Retention: %{z:.1f}%<extra></extra>",
    ))
    fig.update_layout(**_layout("Cohort Retention Heatmap"))
    fig.update_xaxes(side="top")
    return fig


def make_retention_curve():
    """Average retention curve across all cohorts."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=avg_retention["MonthNumber"],
        y=avg_retention["RetentionRate"],
        mode="lines+markers",
        line=dict(color=ACCENT, width=2.5),
        marker=dict(size=7),
        fill="tozeroy",
        fillcolor=f"rgba(46,134,171,0.12)",
        hovertemplate="Month %{x}<br>Avg Retention: %{y:.1f}%<extra></extra>",
        name="Avg Retention",
    ))

    # Month-1 callout line
    m1 = avg_retention.loc[avg_retention["MonthNumber"]==1, "RetentionRate"]
    if not m1.empty:
        m1_val = m1.values[0]
        fig.add_hline(
            y=m1_val,
            line=dict(color="#E84855", dash="dash", width=1.5),
            annotation_text=f"Month 1 avg: {m1_val:.1f}% — only 1 in 5 customers return",
            annotation_font=dict(color="#E84855", size=11),
            annotation_position="top right",
        )

    fig.update_layout(**_layout("Average Customer Retention Curve"))
    fig.update_xaxes(title="Months Since First Purchase", tickmode="linear", dtick=1)
    fig.update_yaxes(title="Avg Retention Rate (%)", range=[0, 105], ticksuffix="%")
    return fig


# ── Shared layout defaults ─────────────────────────────────────────────────────
def _layout(title: str) -> dict:
    return dict(
        title=dict(text=title, font=dict(size=14, color=TEXT_COLOR, family=FONT_FAMILY)),
        paper_bgcolor=CARD_COLOR,
        plot_bgcolor=CARD_COLOR,
        font=dict(color=TEXT_COLOR, family=FONT_FAMILY, size=11),
        margin=dict(t=50, b=40, l=40, r=20),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=TEXT_COLOR, size=10),
        ),
        xaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR),
        yaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR),
    )


# ── KPI card helper ─────────────────────────────────────────────────────────────
def kpi_card(title, value, subtitle="", color=ACCENT):
    return html.Div([
        html.P(title, style={"color": "#9EA3B5", "fontSize": "12px",
                             "marginBottom": "4px", "textTransform": "uppercase",
                             "letterSpacing": "0.05em"}),
        html.H2(value, style={"color": TEXT_COLOR, "fontSize": "28px",
                              "fontWeight": "700", "margin": "0",
                              "borderLeft": f"4px solid {color}",
                              "paddingLeft": "10px"}),
        html.P(subtitle, style={"color": "#6B7280", "fontSize": "11px",
                                "marginTop": "4px"}),
    ], style={
        "background": CARD_COLOR,
        "borderRadius": "10px",
        "padding": "20px 24px",
        "flex": "1",
        "minWidth": "160px",
        "boxShadow": "0 4px 20px rgba(0,0,0,0.3)",
    })


# ══════════════════════════════════════════════════════════════════════════════
# DASH APP LAYOUT
# ══════════════════════════════════════════════════════════════════════════════

app = dash.Dash(
    __name__,
    title="Online Retail — Customer Analytics",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

# Segment dropdown options
seg_options = [{"label": "All Segments", "value": "ALL"}] + [
    {"label": s, "value": s} for s in sorted(customers["Segment"].unique())
]

app.layout = html.Div([

    # ── Header ────────────────────────────────────────────────────────────────
    html.Div([
        html.Div([
            html.H1("Customer Analytics Dashboard",
                    style={"color": TEXT_COLOR, "margin": "0", "fontSize": "22px",
                           "fontWeight": "700"}),
            html.P("Online Retail II · Dec 2009 – Dec 2011 · 5,878 customers · GBP 17.4M revenue",
                   style={"color": "#9EA3B5", "margin": "4px 0 0 0", "fontSize": "12px"}),
        ]),
        html.Div([
            html.Label("Filter by Segment:", style={"color": "#9EA3B5", "fontSize": "12px",
                                                     "marginRight": "10px"}),
            dcc.Dropdown(
                id="segment-filter",
                options=seg_options,
                value="ALL",
                clearable=False,
                style={"width": "220px", "fontSize": "13px"},
            ),
        ], style={"display": "flex", "alignItems": "center"}),
    ], style={
        "background": CARD_COLOR,
        "padding": "18px 32px",
        "display": "flex",
        "justifyContent": "space-between",
        "alignItems": "center",
        "borderBottom": f"2px solid {ACCENT}",
        "boxShadow": "0 2px 12px rgba(0,0,0,0.4)",
    }),

    # ── Tabs ─────────────────────────────────────────────────────────────────
    dcc.Tabs(id="tabs", value="tab-overview",
             style={"backgroundColor": BG_COLOR},
             colors={"border": BG_COLOR, "primary": ACCENT,
                     "background": CARD_COLOR},
             children=[

        # ── TAB 1: OVERVIEW ───────────────────────────────────────────────────
        dcc.Tab(label="📊  Overview", value="tab-overview",
                style={"color": "#9EA3B5", "backgroundColor": CARD_COLOR,
                       "padding": "10px 20px"},
                selected_style={"color": TEXT_COLOR, "backgroundColor": BG_COLOR,
                                "borderTop": f"3px solid {ACCENT}", "padding": "10px 20px"},
                children=[
            html.Div([

                # KPI row
                html.Div([
                    kpi_card("Total Revenue",
                             f"GBP {total_revenue/1e6:.2f}M",
                             "Dec 2009 – Dec 2011"),
                    kpi_card("Total Customers",
                             f"{total_customers:,}",
                             "With purchase history", "#A23B72"),
                    kpi_card("Champion Revenue",
                             f"{champion_rev_pct:.1f}%",
                             f"From {(customers['Segment']=='Champions').sum():,} customers",
                             "#F18F01"),
                    kpi_card("At-Risk Revenue",
                             f"GBP {at_risk_rev/1e6:.2f}M",
                             "At Risk + At Risk - Low Value", "#E84855"),
                    kpi_card("Avg Predicted CLV",
                             f"GBP {avg_clv:,.0f}",
                             "Next 90 days per customer", "#2A9D8F"),
                ], style={"display": "flex", "gap": "16px",
                          "flexWrap": "wrap", "marginBottom": "20px"}),

                # Charts row
                html.Div([
                    html.Div(dcc.Graph(id="donut-chart", config={"displayModeBar": False}),
                             style={"flex": "1", "minWidth": "380px"}),
                    html.Div(dcc.Graph(id="customer-bar", config={"displayModeBar": False}),
                             style={"flex": "1", "minWidth": "380px"}),
                ], style={"display": "flex", "gap": "16px"}),

            ], style={"padding": "24px 32px"}),
        ]),

        # ── TAB 2: REVENUE TRENDS ─────────────────────────────────────────────
        dcc.Tab(label="📈  Revenue & Forecast", value="tab-forecast",
                style={"color": "#9EA3B5", "backgroundColor": CARD_COLOR, "padding": "10px 20px"},
                selected_style={"color": TEXT_COLOR, "backgroundColor": BG_COLOR,
                                "borderTop": f"3px solid {ACCENT}", "padding": "10px 20px"},
                children=[
            html.Div([
                dcc.Graph(id="forecast-chart", figure=make_forecast_chart(),
                          config={"displayModeBar": False},
                          style={"height": "420px", "marginBottom": "16px"}),
                dcc.Graph(id="seasonal-bar", figure=make_seasonal_bar(),
                          config={"displayModeBar": False},
                          style={"height": "320px"}),
            ], style={"padding": "24px 32px"}),
        ]),

        # ── TAB 3: SEGMENTS & CLV ─────────────────────────────────────────────
        dcc.Tab(label="👥  Segments & CLV", value="tab-segments",
                style={"color": "#9EA3B5", "backgroundColor": CARD_COLOR, "padding": "10px 20px"},
                selected_style={"color": TEXT_COLOR, "backgroundColor": BG_COLOR,
                                "borderTop": f"3px solid {ACCENT}", "padding": "10px 20px"},
                children=[
            html.Div([
                html.Div([
                    html.Div(dcc.Graph(id="rfm-scatter", config={"displayModeBar": False}),
                             style={"flex": "1.4", "minWidth": "450px"}),
                    html.Div(dcc.Graph(id="clv-bar", config={"displayModeBar": False}),
                             style={"flex": "1", "minWidth": "320px"}),
                ], style={"display": "flex", "gap": "16px", "marginBottom": "16px"}),

                # Top customers table
                html.H4("Top 20 Customers by Predicted CLV (Next 90 Days)",
                        style={"color": TEXT_COLOR, "marginBottom": "10px",
                               "fontSize": "14px", "fontWeight": "600"}),
                html.Div(id="top-customers-table"),

            ], style={"padding": "24px 32px"}),
        ]),

        # ── TAB 4: COHORT ─────────────────────────────────────────────────────
        dcc.Tab(label="🔁  Cohort Retention", value="tab-cohort",
                style={"color": "#9EA3B5", "backgroundColor": CARD_COLOR, "padding": "10px 20px"},
                selected_style={"color": TEXT_COLOR, "backgroundColor": BG_COLOR,
                                "borderTop": f"3px solid {ACCENT}", "padding": "10px 20px"},
                children=[
            html.Div([
                html.Div([
                    html.P(
                        "Each row is a group of customers acquired in the same month. "
                        "Values show what % of that group made another purchase in each subsequent month. "
                        "Month 0 is always 100% — it's the month they first bought.",
                        style={"color": "#9EA3B5", "fontSize": "12px", "marginBottom": "12px"},
                    ),
                ]),
                dcc.Graph(id="cohort-heatmap", figure=make_cohort_heatmap(),
                          config={"displayModeBar": False},
                          style={"height": "500px", "marginBottom": "16px"}),
                dcc.Graph(id="retention-curve", figure=make_retention_curve(),
                          config={"displayModeBar": False},
                          style={"height": "320px"}),
            ], style={"padding": "24px 32px"}),
        ]),
    ]),

    # Footer
    html.Div(
        "Online Retail II Customer Analytics · Data: UCI ML Repository · "
        "Built with Plotly Dash",
        style={"textAlign": "center", "color": "#4B5563", "fontSize": "11px",
               "padding": "14px", "borderTop": f"1px solid {GRID_COLOR}"},
    ),

], style={
    "fontFamily": FONT_FAMILY,
    "backgroundColor": BG_COLOR,
    "minHeight": "100vh",
    "color": TEXT_COLOR,
})


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS (respond to segment filter)
# ══════════════════════════════════════════════════════════════════════════════

@app.callback(
    Output("donut-chart", "figure"),
    Output("customer-bar", "figure"),
    Output("rfm-scatter", "figure"),
    Output("clv-bar", "figure"),
    Output("top-customers-table", "children"),
    Input("segment-filter", "value"),
)
def update_charts(segment):
    """Recompute all filtered charts when segment dropdown changes."""
    filtered = customers if segment == "ALL" else customers[customers["Segment"] == segment]

    # Recompute segment summary for filtered data
    fs = (
        filtered.groupby("Segment")
        .agg(Customers=("CustomerID","count"), TotalRevenue=("Monetary","sum"))
        .reset_index().sort_values("TotalRevenue", ascending=False)
    )

    # Donut
    colors_d = [SEG_COLORS.get(s, "#BFC0C0") for s in fs["Segment"]]
    donut = go.Figure(go.Pie(
        labels=fs["Segment"], values=fs["TotalRevenue"], hole=0.55,
        marker_colors=colors_d, textinfo="label+percent", textfont_size=11,
        hovertemplate="<b>%{label}</b><br>Revenue: GBP %{value:,.0f}<extra></extra>",
    ))
    total = fs["TotalRevenue"].sum()
    donut.add_annotation(text=f"GBP {total/1e6:.1f}M", x=0.5, y=0.5, showarrow=False,
                         font=dict(size=18, color=TEXT_COLOR, family=FONT_FAMILY))
    donut.update_layout(**_layout("Revenue by Segment"))

    # Customer bar
    fs_sorted = fs.sort_values("Customers")
    colors_b = [SEG_COLORS.get(s, "#BFC0C0") for s in fs_sorted["Segment"]]
    cbar = go.Figure(go.Bar(
        x=fs_sorted["Customers"], y=fs_sorted["Segment"], orientation="h",
        marker_color=colors_b,
        text=fs_sorted["Customers"].apply(lambda x: f"{x:,}"),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Customers: %{x:,}<extra></extra>",
    ))
    cbar.update_layout(**_layout("Customer Count by Segment"))
    cbar.update_xaxes(showgrid=True, gridcolor=GRID_COLOR)

    # Scatter
    scatter = px.scatter(
        filtered, x="Recency", y="Frequency",
        color="Segment", size="Monetary",
        color_discrete_map=SEG_COLORS,
        hover_data={"CustomerID": True, "Monetary": ":.0f"},
        labels={"Recency": "Days Since Last Purchase", "Frequency": "Number of Orders"},
        size_max=25,
    )
    scatter.update_traces(marker=dict(opacity=0.7, line=dict(width=0.5, color="white")))
    scatter.update_layout(**_layout("Customer Map: Recency vs Frequency"))

    # CLV bar
    clv_seg = (
        filtered.groupby("Segment")["predicted_clv_90d"]
        .mean().reset_index().sort_values("predicted_clv_90d")
        .rename(columns={"predicted_clv_90d": "AvgCLV"})
    )
    colors_c = [SEG_COLORS.get(s, "#BFC0C0") for s in clv_seg["Segment"]]
    clv_fig = go.Figure(go.Bar(
        x=clv_seg["AvgCLV"], y=clv_seg["Segment"], orientation="h",
        marker_color=colors_c,
        text=clv_seg["AvgCLV"].apply(lambda x: f"GBP {x:,.0f}"),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Avg CLV (90d): GBP %{x:,.0f}<extra></extra>",
    ))
    clv_fig.update_layout(**_layout("Avg Predicted CLV — Next 90 Days"))
    clv_fig.update_xaxes(tickprefix="GBP ")

    # Top customers table
    top20 = (
        filtered.nlargest(20, "predicted_clv_90d")[
            ["CustomerID", "Segment", "Recency", "Frequency", "Monetary", "predicted_clv_90d"]
        ].rename(columns={
            "Recency": "Recency (days)",
            "Frequency": "Orders",
            "Monetary": "Total Spend (GBP)",
            "predicted_clv_90d": "Predicted CLV 90d (GBP)",
        })
    )
    top20["Total Spend (GBP)"] = top20["Total Spend (GBP)"].map(lambda x: f"{x:,.0f}")
    top20["Predicted CLV 90d (GBP)"] = top20["Predicted CLV 90d (GBP)"].map(lambda x: f"{x:,.0f}")

    table = dash_table.DataTable(
        data=top20.to_dict("records"),
        columns=[{"name": c, "id": c} for c in top20.columns],
        style_table={"overflowX": "auto"},
        style_cell={
            "backgroundColor": CARD_COLOR, "color": TEXT_COLOR,
            "border": f"1px solid {GRID_COLOR}", "padding": "8px 12px",
            "fontSize": "12px", "fontFamily": FONT_FAMILY,
        },
        style_header={
            "backgroundColor": "#252836", "color": ACCENT,
            "fontWeight": "bold", "border": f"1px solid {GRID_COLOR}",
        },
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#1E2130"},
        ],
        page_size=20,
    )
    return donut, cbar, scatter, clv_fig, table


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  Customer Analytics Dashboard")
    print("  Open in browser: http://127.0.0.1:8050")
    print("="*55 + "\n")
    app.run(debug=False, host="127.0.0.1", port=8050)
