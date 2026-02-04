import pandas as pd
import numpy as np

from dash import Dash, dcc, html, Input, Output, State
from dash import ctx, no_update
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go


# ---------- Config ----------
CSV_PATH = "funding_rate_value_monthly_wide.csv"
BOOTSTRAP_THEME = dbc.themes.DARKLY


# ---------- Data loading ----------
def load_data(csv_path: str) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(csv_path, sep=";")

    df["month"] = pd.to_datetime(df["month"], format="%Y-%m")
    df = df.sort_values("month").reset_index(drop=True)

    meta_cols = {"month", "start_timestamp_ms", "end_timestamp_ms"}
    instr_cols = [c for c in df.columns if c not in meta_cols]

    for c in instr_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    return df, instr_cols


DF_WIDE, INSTRUMENTS = load_data(CSV_PATH)

DF_LONG = DF_WIDE.melt(
    id_vars=["month"],
    value_vars=INSTRUMENTS,
    var_name="instrument",
    value_name="funding_dec",
).sort_values(["month", "instrument"])

DF_LONG["cum_dec"] = DF_LONG.groupby("instrument")["funding_dec"].cumsum()


# ---------- Units ----------
UNITS = {
    "dec": {"label": "Decimal", "mult": 1.0, "suffix": "", "fmt": ".6f"},
    "pct": {"label": "%",       "mult": 100.0, "suffix": "%", "fmt": ".3f"},
    "bp":  {"label": "bp",      "mult": 10000.0, "suffix": " bp", "fmt": ".1f"},
}

def apply_units(series: pd.Series, unit_key: str) -> pd.Series:
    return series * UNITS[unit_key]["mult"]

def y_label(unit_key: str, annualized: bool) -> str:
    base = f"Funding ({UNITS[unit_key]['label']})"
    return base + (" — annualized (×12)" if annualized else " — monthly")


def make_monthly_fig(df_long: pd.DataFrame, selected: list[str], unit_key: str, annualized: bool):
    dff = df_long[df_long["instrument"].isin(selected)].copy()

    y = apply_units(dff["funding_dec"], unit_key)
    if annualized:
        y = y * 12.0
    dff["y"] = y

    fig = px.line(
        dff,
        x="month",
        y="y",
        color="instrument",
        markers=True,
        title="Monthly funding",
        labels={"month": "Month", "y": y_label(unit_key, annualized), "instrument": "Instrument"},
    )

    fig.update_layout(
        template="plotly_dark",
        hovermode="x unified",
        legend_title_text="",
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


def make_cum_fig(df_long: pd.DataFrame, selected: list[str], unit_key: str, show_total: bool):
    dff = df_long[df_long["instrument"].isin(selected)].copy()

    dff["y"] = apply_units(dff["cum_dec"], unit_key)

    fig = px.line(
        dff,
        x="month",
        y="y",
        color="instrument",
        title="Cumulative funding",
        labels={"month": "Month", "y": f"Cumulative ({UNITS[unit_key]['label']})", "instrument": "Instrument"},
    )
    fig.update_layout(
        template="plotly_dark",
        hovermode="x unified",
        legend_title_text="",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    if show_total and selected:
        total = (
            dff.groupby("month", as_index=False)["funding_dec"].sum()
            .sort_values("month")
        )
        total["cum_total_dec"] = total["funding_dec"].cumsum()
        total["y_total"] = apply_units(total["cum_total_dec"], unit_key)

        fig.add_trace(
            go.Scatter(
                x=total["month"],
                y=total["y_total"],
                mode="lines",
                name="TOTAL (selected)",
                line=dict(width=4),
            )
        )

    return fig


def make_heatmap(df_wide: pd.DataFrame, selected: list[str], unit_key: str):
    cols = selected[:] if selected else INSTRUMENTS[:]
    z = apply_units(df_wide[cols], unit_key).to_numpy()

    fig = go.Figure(
        data=go.Heatmap(
            x=cols,
            y=df_wide["month"],
            z=z,
            colorbar=dict(title=f"{UNITS[unit_key]['label']}"),
        )
    )
    fig.update_layout(
        template="plotly_dark",
        title="Heatmap (month × instrument)",
        margin=dict(l=20, r=20, t=60, b=20),
        yaxis=dict(title="Month"),
        xaxis=dict(title="Instrument"),
    )
    return fig


def make_stats_table(df_wide: pd.DataFrame, selected: list[str], unit_key: str) -> pd.DataFrame:
    cols = selected if selected else INSTRUMENTS
    dff = df_wide[["month"] + cols].copy().sort_values("month")

    dff["year"] = dff["month"].dt.year

    last_month = dff.iloc[-1]
    last_12m = dff.tail(12)

    # Yearly totals (sum of monthly funding within each calendar year)
    yearly = (
        dff.groupby("year")[cols]
        .sum()
        .sort_index()
    )  # index = year, columns = instruments

    rows = []
    for c in cols:
        total_dec = float(dff[c].sum())
        last_dec = float(last_month[c])
        sum_12m_dec = float(last_12m[c].sum())

        row = {
            "Instrument": c,
            "Latest month": last_dec,
            "Last 12m sum": sum_12m_dec,
            "Total (all time)": total_dec,
        }

        # Add a column for each calendar year, e.g. 2023, 2024, ...
        for y in yearly.index:
            row[str(int(y))] = float(yearly.loc[y, c])

        rows.append(row)

    out = pd.DataFrame(rows)

    # Convert units for display (including year columns)
    unit_mult = UNITS[unit_key]["mult"]
    numeric_cols = [c for c in out.columns if c != "Instrument"]
    out[numeric_cols] = out[numeric_cols].astype(float) * unit_mult

    # Sort by total
    out = out.sort_values("Total (all time)", ascending=False).reset_index(drop=True)

    # Optional: put year columns after the core stats, newest year first
    year_cols = sorted([c for c in out.columns if c.isdigit()], reverse=True)
    out = out[["Instrument", "Latest month", "Last 12m sum", "Total (all time)"] + year_cols]

    return out


def df_to_bootstrap_table(df: pd.DataFrame, unit_key: str):
    df2 = df.copy()

    # Table-specific formatting
    if unit_key == "pct":
        fmt = ".2f"        # <-- 2 decimal places for %
    else:
        fmt = UNITS[unit_key]["fmt"]

    suf = UNITS[unit_key]["suffix"]

    for col in df2.columns:
        if col == "Instrument":
            continue
        df2[col] = (
            pd.to_numeric(df2[col], errors="coerce")
            .fillna(0.0)
            .map(lambda x: f"{x:{fmt}}{suf}")
        )

    return dbc.Table.from_dataframe(
        df2,
        striped=True,
        bordered=False,
        hover=True,
        responsive=True,
        size="sm",
        color="dark",
        className="mb-0",
    )


# ---------- App ----------
app = Dash(__name__, external_stylesheets=[BOOTSTRAP_THEME])
app.title = "Funding Dashboard"

app.layout = dbc.Container(
    fluid=True,
    children=[
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H2("Funding Dashboard", className="mt-3 mb-1"),
                        html.Div(
                            "Beta",
                            className="text-muted mb-3",
                        ),
                    ],
                    width=12,
                )
            ]
        ),

        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.Div("Instruments", className="mb-2"),
                                dcc.Dropdown(
                                    id="instrument-dropdown",
                                    options=[{"label": c, "value": c} for c in INSTRUMENTS],
                                    value=[c for c in INSTRUMENTS if c.startswith(("BTC", "ETH", "SOL"))] or INSTRUMENTS[:3],
                                    multi=True,
                                    placeholder="Select instruments...",
                                ),
                                dbc.Row(
                                    [
                                        dbc.Col(dbc.Button("Select all", id="btn-all", color="secondary", className="mt-2", size="sm"), width="auto"),
                                        dbc.Col(dbc.Button("Select none", id="btn-none", color="secondary", className="mt-2", size="sm"), width="auto"),
                                    ],
                                    className="g-2",
                                ),

                                html.Hr(className="my-3"),

                                html.Div("Units", className="mb-2"),
                                dbc.RadioItems(
                                    id="units-radio",
                                    options=[
                                        {"label": "Decimal", "value": "dec"},
                                        {"label": "%", "value": "pct"},
                                        {"label": "bp", "value": "bp"},
                                    ],
                                    value="pct",
                                    inline=True,
                                ),

                                dbc.Checklist(
                                    id="annualize-check",
                                    options=[{"label": " Show monthly chart as annualized equivalent (×12)", "value": "ann"}],
                                    value=[],
                                    className="mt-2",
                                    switch=True,
                                ),

                                html.Hr(className="my-3"),

                                dbc.Checklist(
                                    id="show-total",
                                    options=[{"label": " Show TOTAL (selected) on cumulative chart", "value": "show"}],
                                    value=["show"],
                                    className="mt-3",
                                    switch=True,
                                ),
                            ]
                        ),
                        className="mb-3",
                    ),
                    width=3,
                ),

                dbc.Col(
                    [
                        dbc.Card(dbc.CardBody(dcc.Graph(id="monthly-graph", config={"displaylogo": False})), className="mb-3"),
                        dbc.Card(dbc.CardBody(dcc.Graph(id="cumulative-graph", config={"displaylogo": False})), className="mb-3"),
                    ],
                    width=9,
                ),
            ]
        ),

        # Heatmap row
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            dcc.Graph(id="heatmap-graph", config={"displaylogo": False})
                        )
                    ),
                    width=12,
                ),
            ],
            className="mb-3",
        ),

        # Quick stats table row (full width)
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Quick stats", className="mb-2"),
                                html.Div(id="stats-table"),
                            ]
                        )
                    ),
                    width=12,
                ),
            ],
            className="mb-4",
        ),
    ],
)


# ---------- Callbacks ----------
@app.callback(
    Output("instrument-dropdown", "value"),
    Input("btn-all", "n_clicks"),
    Input("btn-none", "n_clicks"),
    prevent_initial_call=True,
)
def select_all_none(n_all, n_none):
    trigger = ctx.triggered_id

    if trigger == "btn-all":
        return INSTRUMENTS
    if trigger == "btn-none":
        return []
    return no_update


@app.callback(
    Output("monthly-graph", "figure"),
    Output("cumulative-graph", "figure"),
    Output("heatmap-graph", "figure"),
    Output("stats-table", "children"),
    Input("instrument-dropdown", "value"),
    Input("units-radio", "value"),
    Input("annualize-check", "value"),
    Input("show-total", "value"),
)
def update_charts(selected, unit_key, annualize_value, show_total_value):
    selected = selected or []

    # Fallback if nothing selected
    if not selected:
        preferred = [c for c in INSTRUMENTS if c.startswith(("BTC", "ETH", "SOL"))]
        selected = preferred[:3] if preferred else INSTRUMENTS[:3]

    annualized = "ann" in (annualize_value or [])
    show_total = "show" in (show_total_value or [])

    monthly_fig = make_monthly_fig(DF_LONG, selected, unit_key, annualized)
    cum_fig = make_cum_fig(DF_LONG, selected, unit_key, show_total)
    heatmap_fig = make_heatmap(DF_WIDE, selected, unit_key)

    stats_df = make_stats_table(DF_WIDE, selected, unit_key)
    table = df_to_bootstrap_table(stats_df, unit_key)

    return monthly_fig, cum_fig, heatmap_fig, table


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)
