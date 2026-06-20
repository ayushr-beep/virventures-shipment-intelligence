"""
Virventures Premium Theme — v2: restrained accent, left-rail navigation.

Design plan (revised per reference: left-nav SaaS dashboard, sparing accent):
  Color: White #FFFFFF (dominant bg), Charcoal #1A1C22 (deepened further —
         near-black for the "spotlight" dark card and primary text, matching
         the reference's black stat-card move), Burnt Orange #D2691E
         (RESERVED — active nav state, one spotlight card, the single most
         important number per view — NOT a wash across every element),
         Light Grey #F7F7F8 (page background / inactive surfaces),
         Slate #6B7280 (secondary text), Border Grey #E5E5E7.
  Layout signature: persistent icon-only left rail (mirrors the reference's
         left sidebar) + a dense multi-widget dashboard grid replacing the
         previous stacked single-column layout.
  Restraint: accent color appears on at most 2-3 elements per screen. The
         rest of the UI is monochrome (white/grey/charcoal/black), which is
         what makes the reference read as premium rather than "branded."
"""

VIRVENTURES_THEME_CSS = """
<style>
:root {
    --vv-white: #FFFFFF;
    --vv-near-black: #1A1C22;
    --vv-charcoal: #25272E;
    --vv-orange: #D2691E;
    --vv-orange-dark: #B85A18;
    --vv-bg: #F7F7F8;
    --vv-surface: #FFFFFF;
    --vv-border: #E5E5E7;
    --vv-slate: #6B7280;
    --vv-slate-light: #9CA3AF;
    --vv-shadow-soft: 0 1px 2px rgba(20,20,25,0.04), 0 4px 12px rgba(20,20,25,0.05);
    --vv-shadow-lift: 0 8px 24px rgba(20,20,25,0.10);
    --vv-radius: 14px;
    --vv-radius-sm: 9px;
}

.stApp { background: var(--vv-bg); }
html, body, [class*="css"] {
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    color: var(--vv-charcoal);
}
h1, h2, h3, h4 {
    font-family: Georgia, "Times New Roman", serif !important;
    color: var(--vv-charcoal) !important;
    letter-spacing: -0.01em;
}

/* ---- Left rail (repurposed st.sidebar — icon nav only) ---- */
section[data-testid="stSidebar"] {
    background: var(--vv-near-black);
    border-right: none;
    min-width: 230px !important;
    max-width: 230px !important;
}
section[data-testid="stSidebar"] * { color: #E8E8EA; }
section[data-testid="stSidebar"] .vv-rail-logo {
    display:flex; align-items:center; gap:0.6rem;
    padding: 0.4rem 0 1.4rem 0;
}
.vv-rail-item {
    display:flex; align-items:center; gap:0.7rem;
    padding: 0.65rem 0.8rem;
    border-radius: 10px;
    margin-bottom: 0.2rem;
    font-size: 0.92rem;
    font-weight: 500;
    color: #B8BAC2;
    cursor: pointer;
}
.vv-rail-item.active {
    background: var(--vv-orange);
    color: white;
    font-weight: 600;
}
.vv-rail-item .icon { font-size: 1.05rem; width: 22px; text-align:center; }
.vv-rail-section-label {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #6B6E78;
    margin: 1.1rem 0 0.4rem 0.8rem;
}
section[data-testid="stSidebar"] hr { border-color: #34363E; }

/* Sidebar's native widgets (radio used for nav) styled to look like the rail */
section[data-testid="stSidebar"] div[role="radiogroup"] { gap: 2px; }
section[data-testid="stSidebar"] div[role="radiogroup"] label {
    padding: 0.55rem 0.7rem !important;
    border-radius: 10px !important;
    margin-bottom: 1px;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
    background: rgba(255,255,255,0.06);
}

/* ---- Top utility bar (data upload, assumptions) ---- */
.vv-topbar {
    background: var(--vv-surface);
    border: 1px solid var(--vv-border);
    border-radius: var(--vv-radius);
    padding: 0.9rem 1.2rem;
    margin-bottom: 1rem;
    box-shadow: var(--vv-shadow-soft);
}

/* ---- Spotlight card: the ONE dark/orange moment per view ---- */
.vv-spotlight {
    background: var(--vv-near-black);
    border-radius: var(--vv-radius);
    padding: 1.3rem 1.4rem;
    color: white;
    box-shadow: var(--vv-shadow-lift);
}
.vv-spotlight .vv-spot-label { font-size: 0.74rem; color: #9CA0AC; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; }
.vv-spotlight .vv-spot-value { font-family: Georgia, serif; font-size: 1.9rem; font-weight:700; margin: 0.25rem 0; }
.vv-spotlight .vv-spot-delta { font-size: 0.8rem; color: var(--vv-orange); font-weight:600; }

/* ---- Standard widget card (monochrome — the default) ---- */
.vv-card {
    background: var(--vv-surface);
    border: 1px solid var(--vv-border);
    border-radius: var(--vv-radius);
    padding: 1.1rem 1.2rem;
    box-shadow: var(--vv-shadow-soft);
}
.vv-card-label {
    font-size: 0.74rem; font-weight:700; letter-spacing:0.05em; text-transform:uppercase;
    color: var(--vv-slate); margin-bottom: 0.3rem;
}
.vv-card-value {
    font-family: Georgia, serif; font-size: 1.7rem; font-weight:700; color: var(--vv-charcoal);
}
.vv-card-sub { font-size: 0.8rem; color: var(--vv-slate); margin-top:0.2rem; }

/* ---- Accent card: reserve for ONE key metric per screen ---- */
.vv-card.accent {
    border: 1.5px solid var(--vv-orange);
}
.vv-card.accent .vv-card-value { color: var(--vv-orange-dark); }

/* ---- Mini leaderboard row (SKU list w/ inline stats) ---- */
.vv-leader-row {
    display:flex; align-items:center; justify-content:space-between;
    padding: 0.55rem 0.2rem;
    border-bottom: 1px solid var(--vv-border);
    font-size: 0.86rem;
}
.vv-leader-row:last-child { border-bottom: none; }
.vv-leader-sku { font-weight:600; color: var(--vv-charcoal); }
.vv-leader-chip {
    display:inline-block; padding: 0.15rem 0.55rem; border-radius:6px;
    font-size:0.74rem; font-weight:600; background: var(--vv-bg); color: var(--vv-slate);
}
.vv-leader-chip.hot { background: rgba(210,105,30,0.10); color: var(--vv-orange-dark); }

/* ---- Region tile (kept from v1, restrained) ---- */
.vv-region-tile {
    border-radius: var(--vv-radius); padding: 1.1rem 1rem; text-align:center;
    transition: transform 0.15s ease;
}
.vv-region-tile:hover { transform: translateY(-2px); }
.vv-region-tile.is-top { background: var(--vv-near-black); box-shadow: var(--vv-shadow-lift); }
.vv-region-tile.is-not-top { background: var(--vv-white); border:1px solid var(--vv-border); box-shadow: var(--vv-shadow-soft); }
.vv-region-label { font-size:0.74rem; font-weight:700; letter-spacing:0.08em; }
.vv-region-units { font-family: Georgia, serif; font-size:2.1rem; font-weight:700; margin:0.2rem 0; }
.vv-region-pct { font-size:0.82rem; font-weight:500; }

.vv-eyebrow {
    font-size: 0.74rem; font-weight:700; letter-spacing:0.08em; text-transform:uppercase;
    color: var(--vv-orange-dark); margin-bottom: 0.15rem;
}

/* ---- Native component restraint: tone down st.metric to match monochrome default ---- */
div[data-testid="stMetric"] {
    background: var(--vv-white); border: 1px solid var(--vv-border);
    border-radius: var(--vv-radius); padding: 1rem 1.1rem; box-shadow: var(--vv-shadow-soft);
}
div[data-testid="stMetricLabel"] { color: var(--vv-slate) !important; font-size:0.74rem !important; font-weight:600 !important; letter-spacing:0.05em; text-transform:uppercase; }
div[data-testid="stMetricValue"] { color: var(--vv-charcoal) !important; font-family: Georgia, serif !important; font-weight:700 !important; }

.stButton button, .stDownloadButton button {
    background: var(--vv-near-black); color:white; border:none;
    border-radius: var(--vv-radius-sm); font-weight:600; padding:0.5rem 1.2rem;
    box-shadow: var(--vv-shadow-soft); transition: all 0.15s ease;
}
.stButton button:hover, .stDownloadButton button:hover { background: var(--vv-orange); transform: translateY(-1px); }

.streamlit-expanderHeader { background: var(--vv-white) !important; border-radius: var(--vv-radius-sm) !important; font-weight:600; }
div[data-testid="stExpander"] { border:1px solid var(--vv-border) !important; border-radius: var(--vv-radius) !important; box-shadow: var(--vv-shadow-soft); }
div[data-testid="stDataFrame"] { border-radius: var(--vv-radius-sm); overflow:hidden; box-shadow: var(--vv-shadow-soft); }
div[data-testid="stAlert"] { border-radius: var(--vv-radius-sm); box-shadow: var(--vv-shadow-soft); }

.stSlider [role="slider"] { background-color: var(--vv-orange) !important; }
div[data-baseweb="slider"] > div > div { background: var(--vv-orange) !important; }

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
</style>
"""

NAV_ITEMS = [
    ("dashboard", "📊", "Dashboard"),
    ("quality", "🔍", "Data Quality"),
    ("recommend", "🎯", "Recommendation"),
    ("manifest", "📦", "Shipment Plan"),
    ("export", "📁", "Export"),
    ("setup", "⚙️", "Data & Settings"),
]


def inject_theme(st):
    st.markdown(VIRVENTURES_THEME_CSS, unsafe_allow_html=True)


def render_left_rail(st):
    """
    Renders the icon-based left rail nav inside st.sidebar, using a styled
    st.radio as the actual navigation control (Streamlit has no native
    custom-HTML-clickable-nav that posts back to Python without a component
    library — st.radio styled via CSS is the reliable, dependency-free way
    to get persistent left-nav behavior).
    Returns the selected page key (e.g. "dashboard").
    """
    st.markdown(
        """<div class="vv-rail-logo">
            <div style="width:32px;height:32px;border-radius:8px;background:#D2691E;
                        display:flex;align-items:center;justify-content:center;font-size:1rem;">📦</div>
            <div style="font-family:Georgia,serif;font-weight:700;font-size:1.05rem;color:white;">Virventures</div>
        </div>""",
        unsafe_allow_html=True,
    )

    labels = [f"{icon}  {label}" for _, icon, label in NAV_ITEMS]
    keys = [key for key, _, _ in NAV_ITEMS]

    selected_label = st.radio("Navigate", labels, label_visibility="collapsed", key="vv_nav_radio")
    selected_index = labels.index(selected_label)
    return keys[selected_index]


def render_spotlight_card(st, label, value, delta=None):
    delta_html = f'<div class="vv-spot-delta">{delta}</div>' if delta else ""
    st.markdown(
        f"""<div class="vv-spotlight">
            <div class="vv-spot-label">{label}</div>
            <div class="vv-spot-value">{value}</div>
            {delta_html}
        </div>""",
        unsafe_allow_html=True,
    )


def render_card(st, label, value, sub=None, accent=False):
    sub_html = f'<div class="vv-card-sub">{sub}</div>' if sub else ""
    accent_cls = " accent" if accent else ""
    st.markdown(
        f"""<div class="vv-card{accent_cls}">
            <div class="vv-card-label">{label}</div>
            <div class="vv-card-value">{value}</div>
            {sub_html}
        </div>""",
        unsafe_allow_html=True,
    )


def render_leaderboard_row(st, sku, chips):
    """chips: list of (text, is_hot) tuples rendered as small pill badges."""
    chips_html = "".join(
        f'<span class="vv-leader-chip{" hot" if hot else ""}">{text}</span>&nbsp;'
        for text, hot in chips
    )
    st.markdown(
        f"""<div class="vv-leader-row">
            <span class="vv-leader-sku">{sku}</span>
            <span>{chips_html}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def render_region_tile(st, region_name, units, pct_label, is_top):
    cls = "is-top" if is_top else "is-not-top"
    text_color = "white" if is_top else "#25272E"
    sub_color = "rgba(255,255,255,0.75)" if is_top else "#6B7280"
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

