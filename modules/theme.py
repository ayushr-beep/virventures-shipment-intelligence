"""
Virventures Premium Theme.

Design plan (per frontend-design principles):
  Color: White #FFFFFF (dominant bg), Charcoal #252830 (deepened, primary
         text), Burnt Orange #D2691E (brand accent, unchanged from the
         BMPL pitch deck for identity continuity), Warm Peach #FDF1E7
         (card backgrounds), Slate #6B7280 (secondary text), Deep Amber
         #92400E (data emphasis / large numbers)
  Type:  Georgia/serif for headers (continuity with the BMPL deck identity),
         system sans for body/data (Streamlit's native rendering, weighted
         consistently via CSS overrides)
  Layout signature: oversized KPI numbers mounted on soft warm-white cards
         with a thin orange top-edge highlight (not a full border) and
         layered soft shadows for depth -- restrained "premium SaaS
         dashboard" language without literal 3D render effects, which
         aren't achievable in a live data app.

This module is pure CSS injection via st.markdown(unsafe_allow_html=True).
It does NOT change any Streamlit widget behavior or data logic -- visual
layer only, kept separate from app.py so the styling can be iterated on
without touching application code.
"""

VIRVENTURES_THEME_CSS = """
<style>
/* ============================================================
   VIRVENTURES PREMIUM THEME — orange / white / charcoal
   ============================================================ */

:root {
    --vv-white: #FFFFFF;
    --vv-charcoal: #252830;
    --vv-charcoal-soft: #3A3F4A;
    --vv-orange: #D2691E;
    --vv-orange-dark: #B85A18;
    --vv-orange-light: #E8915A;
    --vv-peach: #FDF1E7;
    --vv-peach-deep: #FBE4CE;
    --vv-slate: #6B7280;
    --vv-slate-light: #9CA3AF;
    --vv-amber-deep: #92400E;
    --vv-border: #EDE6DC;
    --vv-shadow-soft: 0 2px 8px rgba(37, 40, 48, 0.04), 0 8px 24px rgba(37, 40, 48, 0.06);
    --vv-shadow-lift: 0 4px 14px rgba(210, 105, 30, 0.10), 0 12px 32px rgba(37, 40, 48, 0.08);
    --vv-radius: 16px;
    --vv-radius-sm: 10px;
}

/* ---- App background & base typography ---- */
.stApp {
    background: linear-gradient(180deg, #FFFFFF 0%, #FFFCF9 100%);
}
html, body, [class*="css"] {
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    color: var(--vv-charcoal);
}
h1, h2, h3, h4 {
    font-family: Georgia, "Times New Roman", serif !important;
    color: var(--vv-charcoal) !important;
    letter-spacing: -0.01em;
}

/* ---- Sidebar ---- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FFFFFF 0%, #FDF8F3 100%);
    border-right: 1px solid var(--vv-border);
}
section[data-testid="stSidebar"] h1 {
    font-size: 1.3rem !important;
    color: var(--vv-charcoal) !important;
}

/* ---- Tabs: pill-style, premium underline ---- */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: var(--vv-peach);
    padding: 6px;
    border-radius: 14px;
    border: 1px solid var(--vv-border);
}
.stTabs [data-baseweb="tab"] {
    height: 44px;
    border-radius: 10px;
    color: var(--vv-slate);
    font-weight: 600;
    font-size: 0.92rem;
    transition: all 0.18s ease;
}
.stTabs [aria-selected="true"] {
    background: var(--vv-white) !important;
    color: var(--vv-orange-dark) !important;
    box-shadow: var(--vv-shadow-soft);
}

/* ---- Buttons ---- */
.stButton button, .stDownloadButton button {
    background: linear-gradient(135deg, var(--vv-orange) 0%, var(--vv-orange-dark) 100%);
    color: white;
    border: none;
    border-radius: var(--vv-radius-sm);
    font-weight: 600;
    padding: 0.55rem 1.3rem;
    box-shadow: 0 4px 12px rgba(210, 105, 30, 0.22);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.stButton button:hover, .stDownloadButton button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(210, 105, 30, 0.30);
}

/* ---- Native st.metric cards: lifted, soft-shadow tiles ---- */
div[data-testid="stMetric"] {
    background: var(--vv-white);
    border: 1px solid var(--vv-border);
    border-top: 3px solid var(--vv-orange);
    border-radius: var(--vv-radius);
    padding: 1.1rem 1.2rem 0.9rem 1.2rem;
    box-shadow: var(--vv-shadow-soft);
}
div[data-testid="stMetricLabel"] {
    color: var(--vv-slate) !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
div[data-testid="stMetricValue"] {
    color: var(--vv-charcoal) !important;
    font-family: Georgia, serif !important;
    font-weight: 700 !important;
}

/* ---- Expanders: soft card look ---- */
.streamlit-expanderHeader {
    background: var(--vv-peach) !important;
    border-radius: var(--vv-radius-sm) !important;
    font-weight: 600;
    color: var(--vv-charcoal) !important;
}
div[data-testid="stExpander"] {
    border: 1px solid var(--vv-border) !important;
    border-radius: var(--vv-radius) !important;
    box-shadow: var(--vv-shadow-soft);
}

/* ---- Dataframes ---- */
div[data-testid="stDataFrame"] {
    border-radius: var(--vv-radius-sm);
    overflow: hidden;
    box-shadow: var(--vv-shadow-soft);
}

/* ---- Alerts (info/warning/success/error) — soften corners, add depth ---- */
div[data-testid="stAlert"] {
    border-radius: var(--vv-radius-sm);
    box-shadow: var(--vv-shadow-soft);
}

/* ---- Sliders & inputs: orange accent ---- */
.stSlider [role="slider"] {
    background-color: var(--vv-orange) !important;
}
div[data-baseweb="slider"] > div > div {
    background: var(--vv-orange) !important;
}

/* ---- Custom KPI card (used via render_kpi_card helper below) ---- */
.vv-kpi-card {
    background: var(--vv-white);
    border: 1px solid var(--vv-border);
    border-radius: var(--vv-radius);
    padding: 1.3rem 1.4rem;
    box-shadow: var(--vv-shadow-soft);
    position: relative;
    overflow: hidden;
}
.vv-kpi-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--vv-orange) 0%, var(--vv-orange-light) 100%);
}
.vv-kpi-label {
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--vv-slate);
    margin-bottom: 0.35rem;
}
.vv-kpi-value {
    font-family: Georgia, serif;
    font-size: 2.1rem;
    font-weight: 700;
    color: var(--vv-charcoal);
    line-height: 1.1;
}
.vv-kpi-sub {
    font-size: 0.82rem;
    color: var(--vv-slate);
    margin-top: 0.3rem;
}

/* ---- Region split tile (used in Recommendation tab) ---- */
.vv-region-tile {
    border-radius: var(--vv-radius);
    padding: 1.2rem 1rem;
    text-align: center;
    transition: transform 0.15s ease;
}
.vv-region-tile:hover {
    transform: translateY(-2px);
}
.vv-region-tile.is-top {
    background: linear-gradient(155deg, var(--vv-orange) 0%, var(--vv-orange-dark) 100%);
    box-shadow: var(--vv-shadow-lift);
}
.vv-region-tile.is-not-top {
    background: var(--vv-white);
    border: 1px solid var(--vv-border);
    box-shadow: var(--vv-shadow-soft);
}
.vv-region-label {
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
}
.vv-region-units {
    font-family: Georgia, serif;
    font-size: 2.2rem;
    font-weight: 700;
    margin: 0.2rem 0;
}
.vv-region-pct {
    font-size: 0.85rem;
    font-weight: 500;
}

/* ---- Section eyebrow label (small caps header above section titles) ---- */
.vv-eyebrow {
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--vv-orange-dark);
    margin-bottom: 0.15rem;
}

/* ---- Radio buttons styled as segmented control ---- */
div[role="radiogroup"] {
    gap: 0.4rem;
}

/* ---- Hide default Streamlit chrome for a cleaner premium feel ---- */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
</style>
"""


def inject_theme(st):
    """Call once near the top of app.py, right after st.set_page_config."""
    st.markdown(VIRVENTURES_THEME_CSS, unsafe_allow_html=True)


def render_kpi_card(st, label, value, sub=None):
    """Renders a premium KPI card matching the .vv-kpi-card style, as an
    alternative to st.metric for places needing more layout control."""
    sub_html = f'<div class="vv-kpi-sub">{sub}</div>' if sub else ""
    st.markdown(
        f"""<div class="vv-kpi-card">
            <div class="vv-kpi-label">{label}</div>
            <div class="vv-kpi-value">{value}</div>
            {sub_html}
        </div>""",
        unsafe_allow_html=True,
    )


def render_region_tile(st, region_name, units, pct_label, is_top):
    """Renders one region's split as a premium tile -- replaces the inline
    HTML previously built ad-hoc in app.py for region split displays."""
    cls = "is-top" if is_top else "is-not-top"
    text_color = "white" if is_top else "#252830"
    sub_color = "rgba(255,255,255,0.85)" if is_top else "#6B7280"
    st.markdown(
        f"""<div class="vv-region-tile {cls}">
            <div class="vv-region-label" style="color:{sub_color};">{region_name.upper()}</div>
            <div class="vv-region-units" style="color:{text_color};">{units:,}</div>
            <div class="vv-region-pct" style="color:{sub_color};">{pct_label}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_eyebrow(st, text):
    st.markdown(f'<div class="vv-eyebrow">{text}</div>', unsafe_allow_html=True)
