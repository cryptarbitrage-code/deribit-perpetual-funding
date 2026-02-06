import pandas as pd
import numpy as np

from dash import Dash, dcc, html, Input, Output, State
from dash import ctx, no_update
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go


# ---------- Config ----------
CSV_PATH = "funding_rate_value_monthly_backup.csv"
BOOTSTRAP_THEME = dbc.themes.DARKLY

MONTH_OPTIONS = [
    {"label": "Jan", "value": 1}, {"label": "Feb", "value": 2}, {"label": "Mar", "value": 3},
    {"label": "Apr", "value": 4}, {"label": "May", "value": 5}, {"label": "Jun", "value": 6},
    {"label": "Jul", "value": 7}, {"label": "Aug", "value": 8}, {"label": "Sep", "value": 9},
    {"label": "Oct", "value": 10}, {"label": "Nov", "value": 11}, {"label": "Dec", "value": 12},
]

# Years fixed (simple)
VALID_YEARS = list(range(2019, 2027))
YEAR_OPTIONS = [{"label": str(y), "value": y} for y in VALID_YEARS]


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

# NOTE: We still compute all-time cum_dec for other uses if needed,
# but the cumulative chart will recompute within the selected range.
DF_LONG["cum_dec"] = DF_LONG.groupby("instrument")["funding_dec"].cumsum()


def _y_label_pct(annualized: bool) -> str:
    return "Funding (%) — annualized (×12)" if annualized else "Funding (%) — monthly"


def make_monthly_fig(df_long: pd.DataFrame, selected: list[str], annualized: bool):
    dff = df_long[df_long["instrument"].isin(selected)].copy()

    # Always percent
    y = dff["funding_dec"] * 100.0
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
        labels={"month": "Month", "y": _y_label_pct(annualized), "instrument": "Instrument"},
    )

    fig.update_layout(
        template="plotly_dark",
        hovermode="x unified",
        legend_title_text="",
        margin=dict(l=20, r=20, t=60, b=20),
        height=600,
    )
    return fig


def _month_start(year: int, month: int) -> pd.Timestamp:
    return pd.Timestamp(year=year, month=month, day=1)

def _month_end_exclusive(year: int, month: int) -> pd.Timestamp:
    # first day of next month (exclusive end boundary)
    return _month_start(year, month) + pd.offsets.MonthBegin(1)

def _normalize_range(sy: int, sm: int, ey: int, em: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = _month_start(int(sy), int(sm))
    end_excl = _month_end_exclusive(int(ey), int(em))
    # If user picked an inverted range, swap
    if start >= end_excl:
        start, end_excl = _month_start(int(ey), int(em)), _month_end_exclusive(int(sy), int(sm))
    return start, end_excl


def make_cum_fig(
    df_long: pd.DataFrame,
    selected: list[str],
    show_total: bool,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
):
    """
    Cumulative chart rules:
    - ALWAYS percent (never annualised)
    - Recompute cumulative within the selected month window
    - Window defined by start/end year+month (inclusive), with end boundary exclusive
    """
    start_ts, end_excl = _normalize_range(start_year, start_month, end_year, end_month)

    dff = df_long[df_long["instrument"].isin(selected)].copy()
    dff = dff[(dff["month"] >= start_ts) & (dff["month"] < end_excl)].copy()
    dff = dff.sort_values(["instrument", "month"])

    # Recompute cumulative INSIDE the window
    dff["cum_window_dec"] = dff.groupby("instrument")["funding_dec"].cumsum()

    # Always percent
    dff["y"] = dff["cum_window_dec"] * 100.0

    title = f"Cumulative funding (%) — {start_ts.strftime('%Y-%m')} to {(end_excl - pd.offsets.MonthBegin(1)).strftime('%Y-%m')}"

    fig = px.line(
        dff,
        x="month",
        y="y",
        color="instrument",
        title=title,
        labels={"month": "Month", "y": "Cumulative (%)", "instrument": "Instrument"},
    )
    fig.update_layout(
        template="plotly_dark",
        hovermode="x unified",
        legend_title_text="",
        margin=dict(l=20, r=20, t=60, b=20),
        height=600,
    )
    fig.update_yaxes(zeroline=True)

    if show_total and selected:
        total = (
            dff.groupby("month", as_index=False)["funding_dec"].sum()
            .sort_values("month")
        )
        total["cum_total_dec"] = total["funding_dec"].cumsum()
        total["y_total"] = total["cum_total_dec"] * 100.0  # percent

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


def make_stats_table(df_wide: pd.DataFrame, selected: list[str]) -> pd.DataFrame:
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

    # Convert to % for display (including year columns)
    numeric_cols = [c for c in out.columns if c != "Instrument"]
    out[numeric_cols] = out[numeric_cols].astype(float) * 100.0

    # Sort by total
    out = out.sort_values("Total (all time)", ascending=False).reset_index(drop=True)

    # Optional: put year columns after the core stats, newest year first
    year_cols = sorted([c for c in out.columns if c.isdigit()], reverse=True)
    out = out[["Instrument", "Latest month", "Last 12m sum", "Total (all time)"] + year_cols]

    return out


def df_to_bootstrap_table(df: pd.DataFrame):
    df2 = df.copy()

    # Always percent formatting
    fmt = ".2f"
    suf = "%"

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
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    dbc.Row(
                                        [
                                            dbc.Col(html.Div("Cumulative funding range", className="fw-bold")),
                                        ],
                                        className="mb-2"
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(dbc.Label("Start year", className="mb-1"), width="auto"),
                                            dbc.Col(
                                                dcc.Dropdown(
                                                    id="cum-start-year",
                                                    options=YEAR_OPTIONS,
                                                    value=2025,     # set your preferred default
                                                    clearable=False,
                                                    style={"minWidth": "120px"},
                                                ),
                                                width="auto",
                                            ),
                                            dbc.Col(dbc.Label("Start month", className="mb-1"), width="auto"),
                                            dbc.Col(dcc.Dropdown(id="cum-start-month", options=MONTH_OPTIONS, value=1, clearable=False, style={"minWidth": "120px"}), width="auto"),
                                            dbc.Col(html.Div(style={"width": "16px"}), width="auto"),  # spacer
                                            dbc.Col(dbc.Label("End year", className="mb-1"), width="auto"),
                                            dbc.Col(
                                                dcc.Dropdown(
                                                    id="cum-end-year",
                                                    options=YEAR_OPTIONS,
                                                    value=2026,     # set your preferred default
                                                    clearable=False,
                                                    style={"minWidth": "120px"},
                                                ),
                                                width="auto",
                                            ),
                                            dbc.Col(dbc.Label("End month", className="mb-1"), width="auto"),
                                            dbc.Col(dcc.Dropdown(id="cum-end-month", options=MONTH_OPTIONS, value=12, clearable=False, style={"minWidth": "120px"}), width="auto"),
                                        ],
                                        className="g-2 align-items-end",
                                    ),
                                ]
                            ),
                            className="mb-2",
                        ),
                        dbc.Card(dbc.CardBody(dcc.Graph(id="cumulative-graph", config={"displaylogo": False})), className="mb-3"),
                    ],
                    width=9,
                ),
            ]
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
    Output("stats-table", "children"),
    Input("instrument-dropdown", "value"),
    Input("annualize-check", "value"),
    Input("show-total", "value"),
    Input("cum-start-year", "value"),
    Input("cum-start-month", "value"),
    Input("cum-end-year", "value"),
    Input("cum-end-month", "value"),
)
def update_charts(selected, annualize_value, show_total_value, sy, sm, ey, em):
    selected = selected or []

    # Fallback if nothing selected
    if not selected:
        preferred = [c for c in INSTRUMENTS if c.startswith(("BTC", "ETH", "SOL"))]
        selected = preferred[:3] if preferred else INSTRUMENTS[:3]

    annualized = "ann" in (annualize_value or [])
    show_total = "show" in (show_total_value or [])

    # Default range if dropdowns haven't populated for any reason
    sy = sy if sy is not None else 2025
    sm = sm if sm is not None else 1
    ey = ey if ey is not None else 2026
    em = em if em is not None else 12

    monthly_fig = make_monthly_fig(DF_LONG, selected, annualized)

    # Cumulative chart: percent-only + recomputed within window
    cum_fig = make_cum_fig(DF_LONG, selected, show_total, sy, sm, ey, em)

    stats_df = make_stats_table(DF_WIDE, selected)
    table = df_to_bootstrap_table(stats_df)

    return monthly_fig, cum_fig, table


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)
