import json
import subprocess
import sys
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.latency_view import (
    build_page_latency_frame,
    find_largest_slowdown,
    find_unavailable_pages,
)
from remediator.recovery_simulation import simulate_recovery


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MANIFEST_PATH = ROOT / "eval" / "manifest.csv"
FAULTS_PATH = ROOT / "eval" / "faults.csv"
RCA_SCRIPT = ROOT / "rca" / "rca_v1.py"
FAULT_LABELS = {
    "cpu_hog": "CPU load",
    "mem_leak": "Memory growth",
    "net_delay": "Network delay",
}
SERVICE_LABELS = {
    "adservice": "Ad service",
    "cartservice": "Cart service",
    "checkoutservice": "Checkout service",
    "currencyservice": "Currency service",
    "emailservice": "Email service",
    "frontend": "Website",
    "loadgenerator": "Traffic generator",
    "paymentservice": "Payment service",
    "productcatalogservice": "Product catalog",
    "recommendationservice": "Recommendations",
    "redis-cart": "Cart database",
    "shippingservice": "Shipping service",
}

st.set_page_config(
    page_title="Cloud Sentinel | Self-Healing Cloud",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .stApp {
        background:
          radial-gradient(ellipse at 10% 0%, rgba(14, 165, 233, .12), transparent 30%),
          #081321;
        color: #edf4ff;
      }
      [data-testid="stHeader"] {
        background: transparent !important;
        box-shadow: none !important;
      }
      [data-testid="stHeader"] button {
        color: #edf4ff !important;
      }
      [data-testid="stSidebar"] {
        background: #101d2d;
        border-right: 1px solid rgba(148, 163, 184, .2);
      }
      [data-testid="stSidebar"] [data-testid="stIconMaterial"] {
        color: #edf4ff !important;
        font-size: 0 !important;
      }
      [data-testid="stSidebar"] [data-testid="stIconMaterial"]::after {
        content: "";
        display: block;
        width: 9px;
        height: 9px;
        border-right: 2px solid currentColor;
        border-bottom: 2px solid currentColor;
        transform: rotate(135deg);
      }
      [data-testid="stSidebarCollapseButton"] button {
        visibility: visible !important;
        opacity: 1 !important;
        border-radius: 9px !important;
        background: rgba(125, 211, 252, .12) !important;
      }
      [data-testid="stSidebarCollapseButton"] button:hover {
        background: rgba(125, 211, 252, .24) !important;
      }
      [data-testid="stExpandSidebarButton"] {
        visibility: visible !important;
        opacity: 1 !important;
        border-radius: 9px !important;
        background: rgba(125, 211, 252, .12) !important;
        color: #edf4ff !important;
      }
      [data-testid="stExpandSidebarButton"]:hover {
        background: rgba(125, 211, 252, .24) !important;
      }
      [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {
        color: #edf4ff !important;
        font-size: 0 !important;
      }
      [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"]::after {
        content: "";
        display: block;
        width: 9px;
        height: 9px;
        border-right: 2px solid currentColor;
        border-bottom: 2px solid currentColor;
        transform: rotate(-45deg);
      }
      [data-testid="stSidebar"] h2,
      [data-testid="stSidebar"] h3 {
        color: #edf4ff;
      }
      [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        color: #bdcbe0;
      }
      [data-testid="stMetric"] {
        background: linear-gradient(145deg, #14263b, #102034);
        border: 1px solid rgba(148, 163, 184, .2);
        padding: 16px 18px;
        border-radius: 14px;
        min-height: 112px;
        transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
      }
      [data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        border-color: rgba(125, 211, 252, .4);
        box-shadow: 0 12px 28px rgba(2, 8, 23, .22);
      }
      [data-testid="stMetricLabel"] { color: #bdcbe0; font-size: .92rem; }
      [data-testid="stMetricValue"] { color: #f4f8ff; font-size: 1.65rem; }
      [data-testid="stMetricDelta"] {
        color: #b7c9df !important;
        font-size: .84rem;
      }
      .st-key-summary_metrics [data-testid="stHorizontalBlock"] {
        display: grid !important;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
        gap: 14px;
      }
      .st-key-summary_metrics [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        width: auto !important;
        min-width: 0 !important;
        flex: none !important;
      }
      .st-key-summary_metrics [data-testid="stColumn"] {
        animation: dashboard-enter .55s cubic-bezier(.2,.75,.25,1) both;
      }
      .st-key-summary_metrics [data-testid="stColumn"]:nth-child(1) { animation-delay: .06s; }
      .st-key-summary_metrics [data-testid="stColumn"]:nth-child(2) { animation-delay: .14s; }
      .st-key-summary_metrics [data-testid="stColumn"]:nth-child(3) { animation-delay: .22s; }
      .block-container { max-width: 1440px; padding-top: 5.5rem; padding-bottom: 3rem; }
      .hero {
        position: relative;
        overflow: hidden;
        container-type: inline-size;
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        align-items: center;
        grid-template-areas:
          "copy signals"
          "status signals";
        gap: 24px;
        padding: 30px 34px;
        border-radius: 22px;
        background:
          radial-gradient(ellipse at 88% 18%, rgba(56, 189, 248, .2), transparent 34%),
          radial-gradient(ellipse at 0% 100%, rgba(14, 165, 233, .15), transparent 42%),
          linear-gradient(118deg, #102b43 0%, #132743 54%, #1a2545 100%);
        border: 1px solid rgba(125, 211, 252, .3);
        box-shadow: 0 22px 65px rgba(2, 8, 23, .34), inset 0 1px rgba(255,255,255,.06);
        margin-bottom: 18px;
      }
      .hero::before {
        content: "";
        position: absolute;
        width: 260px;
        height: 260px;
        right: 7%;
        top: -175px;
        border: 1px solid rgba(125, 211, 252, .14);
        border-radius: 50%;
        box-shadow: 0 0 0 22px rgba(125, 211, 252, .025), 0 0 0 46px rgba(125, 211, 252, .02);
        pointer-events: none;
        animation: ambient-drift 18s ease-in-out infinite alternate;
      }
      .hero-copy { grid-area: copy; position: relative; z-index: 1; min-width: 0; }
      .hero-brand {
        display: flex;
        align-items: center;
        gap: 16px;
        margin: 10px 0 12px;
      }
      .hero-brand [data-testid="stHeadingWithActionElements"] { flex: 0 0 auto; }
      .hero-brand [data-testid="stHeaderActionElements"] { display: none; }
      .hero-mark {
        display: grid;
        width: 54px;
        height: 54px;
        flex: 0 0 54px;
        place-items: center;
        border: 1px solid rgba(125, 211, 252, .34);
        border-radius: 17px;
        background: linear-gradient(145deg, rgba(56,189,248,.22), rgba(99,102,241,.17));
        box-shadow: 0 8px 22px rgba(2,8,23,.22), inset 0 1px rgba(255,255,255,.1);
        color: #dff7ff;
        font-size: 1.8rem;
      }
      .hero-status {
        grid-area: status;
        justify-self: start;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 9px 12px;
        border: 1px solid rgba(167, 243, 208, .23);
        border-radius: 999px;
        background: rgba(6, 78, 59, .22);
        color: #c9f8e4;
        font-size: .8rem;
        font-weight: 650;
        letter-spacing: .02em;
        white-space: nowrap;
      }
      .hero-status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #5ee0a0;
        box-shadow: 0 0 12px rgba(94, 224, 160, .62);
      }
      .hero-signals {
        grid-area: signals;
        position: relative;
        z-index: 1;
        display: grid;
        gap: 10px;
        width: 150px;
        padding: 15px;
        border: 1px solid rgba(191, 219, 254, .16);
        border-radius: 17px;
        background: rgba(5, 16, 32, .28);
        box-shadow: inset 0 1px rgba(255,255,255,.05);
        animation: signals-enter .65s .12s cubic-bezier(.2,.75,.25,1) both;
      }
      .signal-row {
        display: flex;
        align-items: center;
        gap: 10px;
        color: #d5e7fa;
        font-size: .78rem;
        font-weight: 600;
      }
      .signal-row:nth-child(1) { animation: signal-enter .45s .18s ease-out both; }
      .signal-row:nth-child(2) { animation: signal-enter .45s .27s ease-out both; }
      .signal-row:nth-child(3) { animation: signal-enter .45s .36s ease-out both; }
      .signal-icon {
        display: grid;
        width: 27px;
        height: 27px;
        place-items: center;
        border-radius: 9px;
        background: rgba(56, 189, 248, .13);
        color: #7dd3fc;
        font-size: .9rem;
      }
      .signal-row { transition: transform .18s ease, color .18s ease; }
      .hero-signals:hover .signal-row { transform: translateX(2px); }
      .hero-signals:hover .signal-icon { background: rgba(56, 189, 248, .2); }
      .hero-signals .signal-icon { transition: background .18s ease; }
      .hero-status-dot { animation: status-glow 2.8s ease-in-out infinite; }
      .safety-strip { animation: dashboard-enter .55s .08s cubic-bezier(.2,.75,.25,1) both; }
      .st-key-run_context { animation: dashboard-enter .55s .12s cubic-bezier(.2,.75,.25,1) both; }
      [data-testid="stVegaLiteChart"] {
        animation: chart-enter .7s .12s cubic-bezier(.2,.75,.25,1) both;
      }
      .st-key-page_response_graph [data-testid="stVegaLiteChart"] {
        animation: chart-enter .7s .12s cubic-bezier(.2,.75,.25,1) both;
      }
      @supports (animation-timeline: view()) {
        .st-key-page_response_graph {
          view-timeline-name: --page-response-entry;
          view-timeline-axis: block;
        }
        .st-key-page_response_graph [data-testid="stVegaLiteChart"] {
          animation: graph-slide-into-view 1s linear both;
          animation-timeline: --page-response-entry;
          animation-range: entry 0% entry 100%;
        }
      }
      @keyframes dashboard-enter {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes chart-enter {
        from { opacity: 0; transform: translateX(-32px); }
        to { opacity: 1; transform: translateX(0); }
      }
      @keyframes graph-slide-into-view {
        from { transform: translateX(-48px); }
        to { transform: translateX(0); }
      }
      @keyframes ambient-drift {
        from { transform: translate3d(0, 0, 0); }
        to { transform: translate3d(-12px, 8px, 0); }
      }
      @keyframes signals-enter {
        from { opacity: 0; transform: translateY(9px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes signal-enter {
        from { opacity: 0; transform: translateX(7px); }
        to { opacity: 1; transform: translateX(0); }
      }
      @keyframes status-glow {
        0%, 100% { box-shadow: 0 0 8px rgba(94, 224, 160, .42); }
        50% { box-shadow: 0 0 14px rgba(94, 224, 160, .78); }
      }
      .eyebrow {
        color: #7dd3fc;
        text-transform: uppercase;
        letter-spacing: .13em;
        font-size: .72rem;
        font-weight: 700;
      }
      .hero h1 {
        margin: 0;
        background: linear-gradient(100deg, #ffffff 8%, #d9f4ff 56%, #a5c8ff 100%);
        background-clip: text;
        color: transparent;
        font-size: clamp(2.1rem, 5cqi, 3.75rem);
        font-weight: 780;
        line-height: 1;
        letter-spacing: -.045em;
        white-space: nowrap;
        text-shadow: 0 8px 34px rgba(56, 189, 248, .12);
      }
      .hero p { color: #d7e5f6; margin: 0; font-size: 1.08rem; line-height: 1.6; max-width: 54rem; }
      .safety-strip {
        display: flex;
        align-items: center;
        gap: 11px;
        margin: 14px 0 18px;
        padding: 12px 16px;
        border: 1px solid rgba(125, 211, 252, .14);
        border-radius: 13px;
        background: linear-gradient(90deg, rgba(14, 165, 233, .09), rgba(16, 29, 45, .45));
        color: #c5d5e8;
        font-size: .9rem;
      }
      .safety-icon {
        display: grid;
        width: 30px;
        height: 30px;
        flex: 0 0 30px;
        place-items: center;
        border-radius: 10px;
        background: rgba(56, 189, 248, .14);
        color: #7dd3fc;
      }
      .safety-strip strong { color: #eff8ff; }
      [data-testid="stWidgetLabel"] p { color: #d7e5f6; }
      .st-key-run_context {
        align-self: center;
        margin-top: 14px;
        padding: 12px 16px 13px;
        border: 1px solid rgba(125, 211, 252, .2);
        border-radius: 14px;
        background:
          linear-gradient(115deg, rgba(14, 165, 233, .11), rgba(99, 102, 241, .08)),
          rgba(16, 29, 45, .62);
        box-shadow: inset 0 1px rgba(255,255,255,.045);
      }
      .st-key-run_context [data-testid="stMarkdownContainer"] {
        margin-bottom: 0 !important;
      }
      .st-key-recovery_demo [data-testid="stButton"] button {
        border: 1px solid rgba(125, 211, 252, .42) !important;
        border-radius: 10px !important;
        background: linear-gradient(120deg, #0c5a83, #33458b) !important;
        color: #f2f8ff !important;
        box-shadow: 0 7px 18px rgba(2, 8, 23, .22);
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
      }
      .st-key-recovery_demo [data-testid="stButton"] button:hover {
        transform: translateY(-2px);
        border-color: rgba(125, 211, 252, .72) !important;
        box-shadow: 0 10px 22px rgba(2, 8, 23, .3);
      }
      .run-context-label {
        margin: 0 0 5px;
        color: #7dd3fc;
        font-size: .72rem;
        font-weight: 750;
        letter-spacing: .1em;
        line-height: 1.35;
        text-transform: uppercase;
      }
      .run-context-title {
        color: #e5effb;
        font-size: 1rem;
        line-height: 1.35;
        overflow-wrap: anywhere;
      }
      .run-context-title strong { color: #fff; font-weight: 700; }
      .section-note { color: #c0cfe2; font-size: .95rem; margin-top: -.45rem; }
      [data-testid="stSubheader"] { letter-spacing: -.02em; }
      div[data-testid="stAlert"] { border-radius: 13px; }
      div[data-testid="stAlert"] p { color: #edf4ff; }
      div[data-testid="stDataFrame"] { border: 1px solid rgba(148,163,184,.2); border-radius: 12px; }
      .st-key-raw_readings_table [data-testid="stTable"] {
        max-height: 420px;
        overflow: auto;
        border: 1px solid rgba(148, 163, 184, .18);
        border-radius: 12px;
        background: #102034;
      }
      .st-key-raw_readings_table table { margin: 0; }
      .st-key-raw_readings_table thead {
        position: sticky;
        top: 0;
        z-index: 1;
      }
      [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
        display: inline-flex;
        width: 20px;
        height: 20px;
        align-items: center;
        justify-content: center;
        font-size: 0 !important;
        color: #7dd3fc !important;
      }
      [data-testid="stExpander"] summary {
        border-radius: 12px !important;
        background: #102034 !important;
        color: #edf4ff !important;
        transition: background .18s ease, border-color .18s ease;
      }
      [data-testid="stExpander"] summary:hover {
        background: #172b43 !important;
      }
      [data-testid="stExpander"] details[open] > summary {
        border-bottom-left-radius: 0 !important;
        border-bottom-right-radius: 0 !important;
        background: #132840 !important;
      }
      [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
      [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] p {
        color: #edf4ff !important;
      }
      [data-testid="stExpander"] details[open] > [data-testid="stExpanderDetails"] {
        border: 1px solid rgba(148, 163, 184, .2);
        border-top: 0;
        border-radius: 0 0 12px 12px;
        background: rgba(16, 32, 52, .48);
        padding: 14px 16px;
      }
      [data-testid="stExpander"] summary [data-testid="stIconMaterial"]::after {
        content: "";
        display: block;
        width: 8px;
        height: 8px;
        border-right: 2px solid currentColor;
        border-bottom: 2px solid currentColor;
        transform: rotate(-45deg);
        transition: transform .18s ease;
      }
      [data-testid="stExpander"] details[open] summary [data-testid="stIconMaterial"]::after {
        transform: rotate(45deg);
      }
      @media (max-width: 700px) {
        .block-container { padding: 5rem 1rem 2rem; }
        .hero { padding: 22px; }
        .hero-brand { gap: 12px; }
        .hero-mark { width: 46px; height: 46px; flex-basis: 46px; border-radius: 14px; }
        .safety-strip { align-items: flex-start; }
      }
      @container (max-width: 620px) {
        .hero {
          grid-template-columns: minmax(0, 1fr);
          grid-template-areas: "copy" "status";
          gap: 16px;
        }
        .hero-signals { display: none; }
      }
      @container (max-width: 420px) {
        .hero { padding: 18px; }
        .hero-brand { gap: 10px; }
        .hero-mark { width: 42px; height: 42px; flex-basis: 42px; font-size: 1.5rem; }
        .hero h1 { font-size: 1.65rem; }
      }
      @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
          scroll-behavior: auto !important;
          transition-duration: .01ms !important;
          animation: none !important;
        }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_inputs():
    manifest = pd.read_csv(MANIFEST_PATH, dtype=str).fillna("")
    faults = pd.read_csv(FAULTS_PATH, parse_dates=["start", "end"])
    return manifest, faults


def resolve_data_file(filename):
    path = (DATA_DIR / filename).resolve()
    if path.parent != DATA_DIR.resolve() or not path.is_file():
        raise FileNotFoundError(f"Manifest data file is unavailable: {filename}")
    return path


def get_rca_report(csv_path):
    result = subprocess.run(
        [sys.executable, str(RCA_SCRIPT), str(csv_path), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("RCA returned invalid JSON.") from error


def format_seconds(value):
    if pd.isna(value):
        return "—"
    return f"{float(value):.0f} s"


def style_dashboard_table(frame):
    return (
        frame.style
        .set_properties(
            subset=None,
            **{
                "background-color": "#102034",
                "color": "#d7e5f6",
                "border-color": "#26384d",
            }
        )
        .set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("background-color", "#172b43"),
                        ("color", "#9fb4ce"),
                        ("border-color", "#26384d"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [
                        ("background-color", "#102034"),
                        ("color", "#d7e5f6"),
                        ("border-color", "#26384d"),
                    ],
                },
                {
                    "selector": "tbody tr:nth-child(even) td",
                    "props": [("background-color", "#132840")],
                },
            ]
        )
    )


try:
    manifest, faults = load_inputs()
except Exception as error:
    st.error(f"Could not load project evaluation inputs: {error}")
    st.stop()

tests = manifest[manifest["role"] == "test"].copy()
if tests.empty:
    st.error("The manifest has no runs marked role='test'.")
    st.stop()

st.sidebar.markdown("## ☁️ Cloud Sentinel")
st.sidebar.caption("Recorded experiment review")
st.sidebar.divider()
st.sidebar.markdown("### Safe mode")
st.sidebar.success("Read-only · No cluster actions")
st.sidebar.caption(
    "This dashboard reviews saved experiment files only. "
    "It cannot restart, scale, or modify services."
)

labels = {
    row["file"]: (
        f"{FAULT_LABELS.get(row['fault'], row['fault'].replace('_', ' ').title())}"
        f" · {SERVICE_LABELS.get(row['service'], row['service'].replace('_', ' ').title())} · "
        f"Run {Path(row['file']).stem.rsplit('_', 1)[-1]}"
    )
    for _, row in tests.iterrows()
}
st.markdown(
    """
    <div class="hero">
      <div class="hero-copy">
        <div class="eyebrow">Cloud operations · Recorded incident review</div>
        <div class="hero-brand">
          <span class="hero-mark" aria-hidden="true">☁</span>
          <h1>Cloud Sentinel</h1>
        </div>
        <p>Turn recorded incident data into clear evidence and a safer next step.</p>
      </div>
      <div class="hero-signals" aria-hidden="true">
        <div class="signal-row"><span class="signal-icon">↗</span>Impact</div>
        <div class="signal-row"><span class="signal-icon">?</span>Evidence</div>
        <div class="signal-row"><span class="signal-icon">✓</span>Next step</div>
      </div>
      <div class="hero-status"><span class="hero-status-dot"></span>Recorded data · Read only</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    <div class="safety-strip">
      <span class="safety-icon" aria-hidden="true">🛡️</span>
      <span><strong>Safe review mode</strong> · Recommendations are suggestions only. No services or cluster settings are changed.</span>
    </div>
    """,
    unsafe_allow_html=True,
)

selector, run_summary = st.columns([1.15, 1])
with selector:
    selected_file = st.selectbox(
        "Select a recorded test",
        options=tests["file"].tolist(),
        format_func=lambda value: labels[value],
    )
if selected_file is None:
    st.error("Select a recorded test to continue.")
    st.stop()
selected = tests[tests["file"] == selected_file].iloc[0]
fault_key = str(selected["fault"])
fault_label = FAULT_LABELS.get(
    fault_key,
    fault_key.replace("_", " ").title(),
)
service_name = str(selected["service"])
service_label = SERVICE_LABELS.get(
    service_name,
    service_name.replace("_", " ").replace("-", " ").title(),
)
with run_summary:
    with st.container(key="run_context"):
        st.markdown(
            f'<div class="run-context-label">Incident review · Run '
            f'{escape(Path(selected_file).stem.rsplit("_", 1)[-1])}</div>'
            f'<div class="run-context-title"><strong>'
            f'{escape(fault_label)}</strong> on '
            f'<strong>{escape(service_label)}</strong></div>',
            unsafe_allow_html=True,
        )

data_path = resolve_data_file(selected_file)
try:
    run_data = pd.read_csv(data_path, parse_dates=["time"])
    rca = get_rca_report(data_path)
except Exception as error:
    st.error(f"Could not analyze {selected_file}: {error}")
    st.stop()

fault_rows = faults[
    (faults["fault"] == selected["fault"])
    & (faults["service"] == selected["service"])
    & (faults["start"] >= run_data["time"].min())
    & (faults["end"] <= run_data["time"].max())
]
if len(fault_rows) != 1:
    st.error(f"Expected one matching fault window; found {len(fault_rows)}.")
    st.stop()
fault = fault_rows.iloc[0]

decision = rca["resource_decision"]
candidate = decision["service"] or "Unknown"
resource_ranking = rca["resource_ranking"]
score = decision["score"]
top_score = f"{score:.2f}" if score is not None else "—"

latency_report = rca["page_latency"]
timeouts_during_fault = sum(
    item["timeouts"] for item in latency_report.values()
)
timeouts_after_fault = sum(
    item["timeouts_after_fault"] for item in latency_report.values()
)

page_frame = build_page_latency_frame(latency_report)
valid_changes = page_frame.dropna(subset=["Change (seconds)"])
largest_slowdown = find_largest_slowdown(page_frame)

raised_measure = "resource use"
if decision["status"] == "candidate":
    if not resource_ranking:
        st.error(
            "The analysis suggested a service to investigate but did not provide "
            "supporting measurements."
        )
        st.stop()
    evidence = resource_ranking[0]["evidence"]
    raised_measure = (
        "CPU use"
        if evidence["cpu_cores"]["rise_score"]
        >= evidence["memory_mb"]["rise_score"]
        else "memory use"
    )

st.subheader("Incident overview")
with st.container(key="summary_metrics"):
    metric_columns = st.columns(3)
    if decision["status"] == "candidate":
        metric_columns[0].metric(
            "Service to investigate",
            SERVICE_LABELS.get(candidate, candidate.replace("_", " ").title()),
            f"{raised_measure[0].upper()}{raised_measure[1:]} increased",
            delta_color="off",
        )
    else:
        metric_columns[0].metric(
            "Service to investigate",
            "No clear lead",
            delta_color="off",
        )
    if largest_slowdown is not None:
        metric_columns[1].metric(
            "Increase in page load time",
            f"+{largest_slowdown[1]:.2f} s",
            f"{largest_slowdown[0]} page · above baseline",
            delta_color="off",
        )
    elif not valid_changes.empty:
        fastest_change = min(
            valid_changes.to_dict("records"),
            key=lambda row: row["Change (seconds)"],
        )
        change = float(fastest_change["Change (seconds)"])
        if change < -0.01:
            metric_columns[1].metric(
                "Page-load change",
                "No increase",
                delta_color="off",
            )
        else:
            metric_columns[1].metric(
                "Page-load change",
                "No change",
                delta_color="off",
            )
    else:
        metric_columns[1].metric(
            "Page-load change",
            "Not measured",
            delta_color="off",
        )
    metric_columns[2].metric(
        "Failed page loads",
        str(timeouts_during_fault) if latency_report else "Not measured",
        "During incident window" if latency_report else "No page-check data",
        delta_color="off",
    )

if timeouts_during_fault:
    timeout_label = "page check" if timeouts_during_fault == 1 else "page checks"
    after_timeout_label = "page check" if timeouts_after_fault == 1 else "page checks"
    after_fault_note = (
        f" {timeouts_after_fault} additional {after_timeout_label} did not complete "
        "after the incident window."
        if timeouts_after_fault
        else ""
    )
    st.error(
        f"{timeouts_during_fault} {timeout_label} did not complete during the incident. "
        "These checks failed to load; they are not slow completed responses."
        f"{after_fault_note}"
    )
elif timeouts_after_fault:
    after_timeout_label = "page check" if timeouts_after_fault == 1 else "page checks"
    st.warning(
        f"{timeouts_after_fault} {after_timeout_label} did not complete "
        "after the incident window."
    )

if decision["status"] == "candidate":
    st.info(
        f"The measurements show higher {raised_measure} on "
        f"**{SERVICE_LABELS.get(candidate, candidate.replace('_', ' ').title())}** "
        "during the incident window. Treat this as an investigation lead, not a confirmed cause."
    )
elif largest_slowdown is not None:
    st.info(
        f"**{largest_slowdown[0]}** took about {largest_slowdown[1]:.2f} seconds longer "
        "to load. This confirms a customer-visible slowdown, but does not identify its cause."
    )
elif not valid_changes.empty:
    st.info(
        "No clear slowdown appears in the recorded page data. This does not rule out "
        "an issue on pages or services that were not measured."
    )
else:
    st.info(
        "There are no completed page-load measurements to assess impact. "
        "Review the timeout count and coverage note before drawing a conclusion."
    )

st.subheader("Self-healing simulation")
st.caption(
    "The selected recording supplies the fault type and investigation lead. "
    "This demo uses synthetic in-memory metrics only; it does not change the "
    "recording, restart a real service, or connect to Kubernetes."
)
with st.container(key="recovery_demo"):
    recovery_key = f"recovery_simulation_{selected_file}"
    if decision["status"] != "candidate":
        st.info(
            "No supported service lead was identified, so the recovery simulation "
            "is unavailable for this run."
        )
    elif fault_key not in {"cpu_hog", "mem_leak", "net_delay"}:
        st.info("No allowlisted sandbox recovery scenario exists for this fault type.")
    else:
        if st.button("Run sandbox recovery", key="run_recovery_simulation"):
            st.session_state[recovery_key] = simulate_recovery(fault_key, candidate)
        simulation = st.session_state.get(recovery_key)
        if simulation is not None:
            st.success(
                f"Sandbox detected the simulated fault on "
                f"**{SERVICE_LABELS.get(simulation.target_service, simulation.target_service)}**."
            )
            st.write(simulation.detected_signal)
            before_column, action_column, after_column = st.columns(3)
            with before_column:
                st.metric(
                    "Sandbox before action",
                    f"{simulation.before.cpu_percent:.0f}% CPU",
                    f"{simulation.before.memory_mb:.0f} MB · "
                    f"{simulation.before.latency_ms:.0f} ms",
                    delta_color="off",
                )
            with action_column:
                st.markdown("**Simulated recovery action**")
                st.write(simulation.action)
            with after_column:
                st.metric(
                    "Sandbox after action",
                    f"{simulation.after.cpu_percent:.0f}% CPU",
                    f"{simulation.after.memory_mb:.0f} MB · "
                    f"{simulation.after.latency_ms:.0f} ms",
                    delta_color="off",
                )
            if simulation.recovered:
                st.success(
                    "Simulated health check passed. The sandbox metrics returned "
                    "within their demonstration limits."
                )
            else:
                st.error("The simulated health check failed; the sandbox remains unhealthy.")

st.subheader("Customer impact · Page response")
st.markdown(
    '<p class="section-note">Typical load time before and during the incident window. '
    'Hover over a bar to see its exact value.</p>',
    unsafe_allow_html=True,
)
if latency_report:
    chart_frame = page_frame.dropna(
        subset=["Before (seconds)", "During (seconds)"]
    )
    if not chart_frame.empty:
        plot_frame = chart_frame.melt(
            id_vars="Page",
            value_vars=["Before (seconds)", "During (seconds)"],
            var_name="When",
            value_name="Response time (seconds)",
        )
        plot_frame["When"] = plot_frame["When"].replace(
            {
                "Before (seconds)": "Before test",
                "During (seconds)": "During test",
            }
        )
        page_order = ["Home", "Product", "Cart"]
        period_order = ["Before test", "During test"]
        page_axis = alt.X(
            "Page:N",
            title=None,
            sort=page_order,
            axis=alt.Axis(labelAngle=0, labelPadding=10, tickSize=0),
            scale=alt.Scale(
                paddingInner=0.55,
                paddingOuter=0.3,
            ),
        )
        period_offset = alt.XOffset(
            "When:N",
            scale=alt.Scale(domain=period_order),
        )
        load_time = alt.Y(
            "Response time (seconds):Q",
            title="Load time (seconds)",
            scale=alt.Scale(domainMin=0),
            axis=alt.Axis(format=".2f", tickCount=5, grid=True, tickSize=0),
        )
        period_color = alt.Color(
            "When:N",
            title=None,
            scale=alt.Scale(
                domain=period_order,
                range=["#38bdf8", "#fbbf24"],
            ),
            legend=alt.Legend(
                orient="top",
                direction="horizontal",
                labelFontSize=12,
                symbolSize=110,
                symbolStrokeWidth=0,
                padding=4,
            ),
        )
        bars = (
            alt.Chart(plot_frame)
            .mark_bar(size=38, cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
            .encode(
                x=page_axis,
                xOffset=period_offset,
                y=load_time,
                color=period_color,
                tooltip=[
                    alt.Tooltip("Page:N", title="Page"),
                    alt.Tooltip("When:N", title="Period"),
                    alt.Tooltip(
                        "Response time (seconds):Q",
                        title="Typical page-load time (seconds)",
                        format=".3f",
                    ),
                ],
            )
        )
        value_labels = (
            alt.Chart(plot_frame)
            .mark_text(
                dy=-8,
                fontSize=11,
                fontWeight=600,
                color="#e2eaf5",
            )
            .encode(
                x=page_axis,
                xOffset=period_offset,
                y=load_time,
                text=alt.Text("Response time (seconds):Q", format=".2f"),
            )
        )
        chart = (
            (bars + value_labels)
            .properties(height=310)
            .configure(background="#081321")
            .configure_view(stroke=None)
            .configure_axis(
                domain=False,
                gridColor="#26384d",
                gridOpacity=0.8,
                labelColor="#bdcbe0",
                titleColor="#d7e5f6",
                titleFontSize=12,
            )
            .configure_legend(
                labelColor="#d7e5f6",
                titleColor="#edf4ff",
                labelLimit=160,
            )
        )
        with st.container(key="page_response_graph"):
            st.altair_chart(chart, width="stretch")
        unavailable_pages = find_unavailable_pages(page_frame)
        if unavailable_pages:
            unavailable = (
                unavailable_pages[0]
                if len(unavailable_pages) == 1
                else f"{', '.join(unavailable_pages[:-1])} and {unavailable_pages[-1]}"
            )
            st.info(
                f"Coverage note · Readings are available for {', '.join(chart_frame['Page'])} only. "
                f"{unavailable} were not measured, so their impact cannot be assessed from this run."
            )
    else:
        st.info(
            "No completed page loads are available for comparison. "
            "Failed checks, if any, are listed separately above."
        )
else:
    st.info("Page-load data was not captured for this run.")

st.subheader("Recommended follow-up")
if decision["status"] != "candidate":
    st.info(
        "Have an operator review logs and traces around the incident window. "
        "The available measurements do not identify a clear service lead; no changes have been made."
    )
else:
    st.info(
        f"Have an operator verify {raised_measure} and workload on "
        f"**{SERVICE_LABELS.get(candidate, candidate.replace('_', ' ').title())}** "
        "against the incident window. Review the evidence before making any change."
    )

if latency_report:
    with st.expander("Detailed page measurements"):
        st.table(style_dashboard_table(page_frame))

with st.expander("Technical details: service measurements"):
    st.caption(
        "The chart ranks resource changes during the test. The score is a comparison aid, "
        "not a probability or proof that a service caused the issue."
    )
    ranking = pd.DataFrame(resource_ranking)
    if ranking.empty:
        st.info("No comparable service metrics were available.")
    else:
        service_names = ranking["service"].astype(str)
        ranking["Service"] = service_names.map(SERVICE_LABELS).fillna(
            service_names.str.replace("_", " ", regex=False)
            .str.replace("-", " ", regex=False)
            .str.title()
        )
        ranking["score"] = pd.to_numeric(ranking["score"], errors="raise")
        threshold = float(decision["threshold"])
        max_score = float(ranking["score"].max())
        score_axis_max = max(max_score, threshold) * 1.12
        candidate_label = (
            SERVICE_LABELS.get(candidate, candidate.replace("_", " ").title())
            if decision["status"] == "candidate"
            else ""
        )
        service_axis = alt.Y(
            "Service:N",
            title=None,
            sort=alt.EncodingSortField(field="score", order="descending"),
            axis=alt.Axis(labelColor="#d7e5f6", labelLimit=220, tickSize=0),
        )
        score_axis = alt.X(
            "score:Q",
            title="Relative resource-change score",
            scale=alt.Scale(domain=[0, score_axis_max]),
            axis=alt.Axis(format=".2f", tickCount=6, grid=True, tickSize=0),
        )
        service_bars = (
            alt.Chart(ranking)
            .mark_bar(size=18, cornerRadiusEnd=5)
            .encode(
                x=score_axis,
                y=service_axis,
                color=alt.condition(
                    alt.datum.Service == candidate_label,
                    alt.value("#fbbf24"),
                    alt.value("#38bdf8"),
                ),
                tooltip=[
                    alt.Tooltip("Service:N", title="Service"),
                    alt.Tooltip("score:Q", title="Resource-change score", format=".3f"),
                ],
            )
        )
        score_labels = (
            alt.Chart(ranking)
            .mark_text(
                align="left",
                baseline="middle",
                dx=6,
                color="#d7e5f6",
                fontSize=11,
            )
            .encode(
                x=score_axis,
                y=service_axis,
                text=alt.Text("score:Q", format=".2f"),
            )
        )
        threshold_rule = (
            alt.Chart(pd.DataFrame({"threshold": [threshold]}))
            .mark_rule(color="#fbbf24", strokeDash=[5, 4], strokeWidth=2)
            .encode(x=alt.X("threshold:Q", scale=alt.Scale(domain=[0, score_axis_max])))
        )
        service_chart = (
            (service_bars + score_labels + threshold_rule)
            .properties(height=max(350, 30 * len(ranking)))
            .configure(background="#0b1726")
            .configure_view(stroke=None)
            .configure_axis(
                domain=False,
                gridColor="#26384d",
                gridOpacity=0.75,
                labelColor="#bdcbe0",
                titleColor="#d7e5f6",
                titleFontSize=12,
            )
        )
        st.altair_chart(service_chart, width="stretch")
        st.caption(
            f"Dashed line: candidate threshold ({threshold:.1f}). "
            f"Highest score: {max_score:.2f}. "
            "Scores compare resource changes; they are not probabilities."
        )

with st.expander("Technical details: run information"):
    run_details = pd.DataFrame(
        [
            ("Run file", selected_file),
            ("Manifest role", selected["role"]),
            ("Fault", selected["fault"]),
            ("Service under test", selected["service"]),
            ("Fault window", f"{fault['start']} → {fault['end']}"),
            ("Manifest note", selected["note"] or "None"),
            ("Operating mode", "Recorded data only; no action executed"),
        ],
        columns=["Field", "Value"],
    )
    st.table(style_dashboard_table(run_details))

with st.expander("Show raw readings"):
    with st.container(key="raw_readings_table"):
        st.table(style_dashboard_table(run_data.head(100)))