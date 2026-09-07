"""Local read-only terminal for inspecting the reviewed market-data pipeline."""

from datetime import date, datetime, time, timedelta, timezone
from html import escape

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from crypto_trader.data import (
    BinanceKlineAcquisitionError,
    BinanceKlineAcquisitionResult,
    fetch_binance_spot_klines,
)
from crypto_trader.ui import (
    bars_to_chart_values,
    bars_to_table_rows,
    coverage_percentage,
    format_utc_timestamp,
    validation_issues_to_rows,
)

UTC = timezone.utc


def _utc_datetime(day: date, clock: time) -> datetime:
    """Combine user controls into an explicit aware UTC datetime."""
    return datetime.combine(day, clock, tzinfo=UTC)


def _status_card(label: str, value: str, tone: str = "neutral") -> str:
    """Build one escaped status cell for the responsive terminal grid."""
    return (
        f'<div class="status-card {escape(tone)}">'
        f'<div class="status-label">{escape(label)}</div>'
        f'<div class="status-value">{escape(value)}</div></div>'
    )


def _market_figure(result: BinanceKlineAcquisitionResult) -> go.Figure:
    """Build the terminal candlestick and volume figure from trusted bars."""
    values = bars_to_chart_values(result.bars)
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.76, 0.24],
    )
    figure.add_trace(
        go.Candlestick(
            x=values["timestamp"],
            open=values["open"],
            high=values["high"],
            low=values["low"],
            close=values["close"],
            increasing_line_color="#45d6a5",
            decreasing_line_color="#e05d5d",
            name="BTCUSDT",
        ),
        row=1,
        col=1,
    )
    volume_colors = [
        "#45d6a5" if close >= open_ else "#e05d5d"
        for open_, close in zip(values["open"], values["close"], strict=False)
    ]
    figure.add_trace(
        go.Bar(
            x=values["timestamp"],
            y=values["volume"],
            marker_color=volume_colors,
            opacity=0.55,
            name="BASE VOLUME",
        ),
        row=2,
        col=1,
    )
    figure.update_layout(
        height=670,
        margin=dict(l=12, r=12, t=42, b=12),
        paper_bgcolor="#090b0d",
        plot_bgcolor="#090b0d",
        font=dict(family="IBM Plex Mono, Menlo, monospace", color="#b7bec7", size=11),
        title=dict(text="BTCUSDT · 1H · TRUSTED OHLCV · UTC", font=dict(color="#d8a84e", size=13)),
        showlegend=False,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
    )
    figure.update_xaxes(
        gridcolor="#1c2228",
        linecolor="#313942",
        tickformat="%Y-%m-%d\n%H:%M UTC",
        title_text="UTC",
        row=2,
        col=1,
    )
    figure.update_yaxes(gridcolor="#1c2228", linecolor="#313942", title_text="USDT", row=1, col=1)
    figure.update_yaxes(gridcolor="#1c2228", linecolor="#313942", title_text="BTC", row=2, col=1)
    return figure


def _render_status_strip(result: BinanceKlineAcquisitionResult | None) -> None:
    coverage = f"{coverage_percentage(result.coverage):.2f}%" if result else "—"
    missing = str(result.coverage.missing_expected_bar_count) if result else "—"
    sequence_valid = result.sequence_validation.is_valid if result else None
    capped = result.end_was_capped if result else None
    cards = [
        ("SYMBOL", "BTCUSDT", "amber"),
        ("VENUE", "BINANCE SPOT", "neutral"),
        ("INTERVAL", "1H", "neutral"),
        ("BARS", str(len(result.bars)) if result else "—", "neutral"),
        ("COVERAGE", coverage, "good" if result and result.coverage.is_complete else "bad" if result else "neutral"),
        ("MISSING", missing, "good" if result and result.coverage.missing_expected_bar_count == 0 else "bad" if result else "neutral"),
        ("SEQUENCE", "VALID" if sequence_valid else "ISSUES" if sequence_valid is False else "—", "good" if sequence_valid else "bad" if sequence_valid is False else "neutral"),
        ("END CAP", "APPLIED" if capped else "NOT REQUIRED" if capped is False else "—", "amber" if capped else "good" if capped is False else "neutral"),
    ]
    st.markdown(
        '<div class="status-grid">'
        + "".join(_status_card(label, value, tone) for label, value, tone in cards)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_quality(result: BinanceKlineAcquisitionResult) -> None:
    st.markdown('<div class="section-kicker">DATA QUALITY // RANGE ACCOUNTING</div>', unsafe_allow_html=True)
    range_columns = st.columns(3)
    range_columns[0].metric("REQUESTED START", format_utc_timestamp(result.requested_start))
    range_columns[1].metric("REQUESTED END", format_utc_timestamp(result.requested_end))
    range_columns[2].metric("EFFECTIVE END", format_utc_timestamp(result.effective_end))
    st.caption(f"AS OF USED · {format_utc_timestamp(result.as_of)}")

    quality_columns = st.columns(5)
    quality_columns[0].metric("EXPECTED BARS", result.coverage.expected_bar_count)
    quality_columns[1].metric(
        "OBSERVED UNIQUE ALIGNED",
        result.coverage.observed_unique_aligned_bar_count,
    )
    quality_columns[2].metric("MISSING EXPECTED", result.coverage.missing_expected_bar_count)
    quality_columns[3].metric("COVERAGE COMPLETE", "YES" if result.coverage.is_complete else "NO")
    quality_columns[4].metric("SEQUENCE VALID", "YES" if result.sequence_validation.is_valid else "NO")

    if result.end_was_capped:
        st.info(
            "The requested end was reduced to the start of the explicit AS OF UTC hour "
            f"({format_utc_timestamp(result.effective_end)}), excluding candles still open at that AS OF instant."
        )
    else:
        st.success("The requested end required no closed-candle cap.")

    if result.sequence_validation.issues:
        st.markdown('<div class="section-kicker danger">SEQUENCE ISSUES</div>', unsafe_allow_html=True)
        st.dataframe(
            validation_issues_to_rows(result.sequence_validation.issues),
            width="stretch",
            hide_index=True,
        )
    else:
        st.markdown('<div class="quality-ok">SEQUENCE CHECK · VALID</div>', unsafe_allow_html=True)


st.set_page_config(
    page_title="Autonomous AI Crypto Research Terminal",
    page_icon="▰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { --amber:#d8a84e; --green:#45d6a5; --red:#e05d5d; --panel:#101419; --line:#283039; }
    .stApp { background:#07090b; color:#c5cbd2; }
    header[data-testid="stHeader"] { background:rgba(7,9,11,.94); }
    section[data-testid="stSidebar"] { background:#0b0e11; border-right:1px solid var(--line); }
    .block-container { padding-top:4.5rem; padding-bottom:2rem; max-width:1800px; }
    html, body, [class*="css"] { font-family:Inter, system-ui, sans-serif; }
    code, .status-card, .terminal-panel, .section-kicker, .terminal-meta { font-family:"IBM Plex Mono",Menlo,monospace; }
    .terminal-header { border-top:2px solid var(--amber); border-bottom:1px solid var(--line); padding:.75rem 0 .65rem; margin-bottom:.7rem; }
    .terminal-title { color:#f0f2f4; font:600 1.35rem "IBM Plex Mono",Menlo,monospace; letter-spacing:.055em; }
    .terminal-subtitle { color:var(--amber); font:500 .72rem "IBM Plex Mono",Menlo,monospace; letter-spacing:.16em; margin-top:.25rem; }
    .terminal-flags { color:#8f99a3; font:500 .68rem "IBM Plex Mono",Menlo,monospace; letter-spacing:.08em; margin-top:.55rem; }
    .warning-band { border:1px solid #604922; background:#17130c; color:#efc66f; padding:.42rem .65rem; font:600 .72rem "IBM Plex Mono",Menlo,monospace; letter-spacing:.09em; }
    .status-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.45rem; margin-top:.65rem; }
    .status-card { min-width:0; background:var(--panel); border:1px solid var(--line); border-top:2px solid #4a535d; min-height:70px; padding:.55rem .62rem; }
    .status-card.good { border-top-color:var(--green); } .status-card.bad { border-top-color:var(--red); } .status-card.amber { border-top-color:var(--amber); }
    .status-label { color:#76818c; font-size:.62rem; letter-spacing:.11em; }
    .status-value { color:#e2e6e9; font-size:.83rem; font-weight:600; margin-top:.35rem; white-space:normal; overflow-wrap:anywhere; }
    .status-card.good .status-value { color:var(--green); } .status-card.bad .status-value { color:var(--red); } .status-card.amber .status-value { color:var(--amber); }
    .section-kicker { color:var(--amber); border-bottom:1px solid var(--line); padding:.6rem 0 .35rem; margin:1rem 0 .7rem; font-size:.72rem; letter-spacing:.13em; }
    .section-kicker.danger { color:var(--red); }
    .quality-ok { color:var(--green); border-left:2px solid var(--green); background:#0d1715; padding:.55rem .7rem; font:600 .72rem "IBM Plex Mono",Menlo,monospace; }
    .terminal-panel { border:1px solid var(--line); background:var(--panel); padding:.8rem 1rem; font-size:.72rem; line-height:1.8; white-space:pre-wrap; overflow-wrap:anywhere; color:#aab3bc; }
    .terminal-panel b { color:var(--green); font-weight:500; }
    div[data-testid="stMetric"] { background:var(--panel); border-left:1px solid var(--line); padding:.55rem .65rem; }
    div[data-testid="stMetricValue"] { font:600 1rem "IBM Plex Mono",Menlo,monospace; }
    div[data-testid="stMetricValue"] > div, div[data-testid="stMetricLabel"] p { white-space:normal; overflow:visible; overflow-wrap:anywhere; text-overflow:clip; }
    div[data-testid="stMetricLabel"] { font-family:"IBM Plex Mono",Menlo,monospace; letter-spacing:.06em; }
    div[data-testid="stDataFrame"] { border:1px solid var(--line); }
    .stButton > button { width:100%; border-radius:1px; border:1px solid var(--amber); background:#1a150c; color:#efc66f; font:600 .73rem "IBM Plex Mono",Menlo,monospace; letter-spacing:.08em; }
    .stButton > button:hover { border-color:#efc66f; color:#fff1c8; }
    @media (max-width: 900px) { .status-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="terminal-header">
      <div class="terminal-title">AUTONOMOUS AI CRYPTO RESEARCH TERMINAL</div>
      <div class="terminal-subtitle">MARKET INTELLIGENCE // RESEARCH MODE</div>
      <div class="terminal-flags">BTCUSDT &nbsp;·&nbsp; SPOT &nbsp;·&nbsp; 1H &nbsp;·&nbsp; BINANCE &nbsp;·&nbsp; UTC &nbsp;·&nbsp; RESEARCH MODE</div>
    </div>
    <div class="warning-band">RESEARCH ONLY &nbsp; // &nbsp; NO EXECUTION &nbsp; // &nbsp; NO LIVE TRADING</div>
    """,
    unsafe_allow_html=True,
)

now_utc = datetime.now(UTC)
current_hour = now_utc.replace(minute=0, second=0, microsecond=0)

with st.sidebar:
    st.markdown('<div class="section-kicker">ACQUISITION CONTROL</div>', unsafe_allow_html=True)
    start_date = st.date_input("REQUESTED START DATE", value=(current_hour - timedelta(days=7)).date())
    start_time = st.time_input("REQUESTED START TIME (UTC)", value=time(0, 0), step=timedelta(hours=1))
    end_date = st.date_input("REQUESTED END DATE", value=current_hour.date())
    end_time = st.time_input("REQUESTED END TIME (UTC)", value=current_hour.time(), step=timedelta(hours=1))
    use_current_as_of = st.checkbox("USE CURRENT UTC AT FETCH", value=True)
    as_of_date = st.date_input("AS OF DATE", value=now_utc.date(), disabled=use_current_as_of)
    as_of_time = st.time_input(
        "AS OF TIME (UTC)",
        value=now_utc.replace(microsecond=0).time(),
        step=timedelta(minutes=1),
        disabled=use_current_as_of,
    )
    fetch_clicked = st.button("FETCH HISTORICAL DATA", type="primary")
    st.caption("Acquisition occurs once per explicit button action. No polling, retries, or persistence.")

if fetch_clicked:
    try:
        requested_start = _utc_datetime(start_date, start_time)
        requested_end = _utc_datetime(end_date, end_time)
        explicit_as_of = (
            datetime.now(UTC)
            if use_current_as_of
            else _utc_datetime(as_of_date, as_of_time)
        )
        st.session_state["acquisition_result"] = fetch_binance_spot_klines(
            requested_start,
            requested_end,
            as_of=explicit_as_of,
        )
        st.session_state.pop("acquisition_error", None)
    except (BinanceKlineAcquisitionError, TypeError, ValueError) as error:
        st.session_state["acquisition_error"] = str(error)
        st.session_state.pop("acquisition_result", None)

result = st.session_state.get("acquisition_result")
error_message = st.session_state.get("acquisition_error")

_render_status_strip(result)

if error_message:
    st.error(f"ACQUISITION FAILED · {error_message}")

if result is None:
    st.markdown('<div class="section-kicker">MARKET DATA // AWAITING REQUEST</div>', unsafe_allow_html=True)
    st.info("Set an explicit UTC research range and select FETCH HISTORICAL DATA.")
else:
    st.caption(
        "Showing the last successful fetch with the result boundaries and AS OF used below. "
        "Changes to acquisition controls apply only to the next explicit fetch."
    )
    _render_quality(result)
    st.markdown('<div class="section-kicker">MARKET CHART // CLOSED HOURLY CANDLES</div>', unsafe_allow_html=True)
    if result.bars:
        st.plotly_chart(_market_figure(result), width="stretch", config={"displaylogo": False, "scrollZoom": True})
    elif result.coverage.expected_bar_count == 0:
        st.info("No fully closed candles are eligible in the effective requested range.")
    else:
        st.warning(
            "No source observations were returned for the effective requested range. "
            f"All {result.coverage.expected_bar_count} expected hourly bars are missing."
        )

    st.markdown('<div class="section-kicker">TRUSTED OHLCV // NORMALIZED VALUES</div>', unsafe_allow_html=True)
    st.dataframe(
        bars_to_table_rows(result.bars),
        width="stretch",
        hide_index=True,
        height=360,
    )

bottom_left, bottom_right = st.columns([1.25, 1])
with bottom_left:
    st.markdown('<div class="section-kicker">SYSTEM // RESEARCH BOUNDARY</div>', unsafe_allow_html=True)
    st.markdown(
        """<div class="terminal-panel">DATA SOURCE     <b>BINANCE SPOT PUBLIC MARKET DATA</b>
SYMBOL          BTCUSDT
INTERVAL        1H
TIME STANDARD   UTC
MODE            RESEARCH ONLY
EXECUTION       DISABLED
PERSISTENCE     DISABLED
AI AGENTS       NOT ENABLED</div>""",
        unsafe_allow_html=True,
    )

with bottom_right:
    st.markdown('<div class="section-kicker">AI RESEARCH COPILOT</div>', unsafe_allow_html=True)
    st.markdown(
        """<div class="terminal-panel">STATUS          <b>NOT ENABLED IN CURRENT PHASE</b>

Future reviewed phases may use AI to explain research outputs and compare experiments.
No LLM or analytical agent is currently active.</div>""",
        unsafe_allow_html=True,
    )
