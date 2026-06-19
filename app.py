import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

from modules import demand_engine, cost_model, decision_engine, excel_export, pptx_export

st.set_page_config(page_title="Virventures | Master Shipment Intelligence", layout="wide")

REGIONS = ["East", "Central", "West"]
ORANGE = "#D2691E"
CHARCOAL = "#33373D"
SLATE = "#5B6168"
GREY = "#6B7178"
PANEL = "#F4F4F5"

# ---------------------------------------------------------------------------
# Sidebar: data upload + editable assumptions
# ---------------------------------------------------------------------------
st.sidebar.title("Master Shipment Intelligence")
st.sidebar.caption("Virventures · Demand-weighted FBA placement")

st.sidebar.markdown("### 1. Upload Data")
use_sample = st.sidebar.checkbox("Use sample data (Tuffo rain suits)", value=True)

sales_file = st.sidebar.file_uploader("Sales History (.xlsx/.csv)", type=["xlsx", "csv"], disabled=use_sample)
inventory_file = st.sidebar.file_uploader("Inventory by Region (.xlsx/.csv)", type=["xlsx", "csv"], disabled=use_sample)
invoices_file = st.sidebar.file_uploader("Shipment Invoices (.xlsx/.csv)", type=["xlsx", "csv"], disabled=use_sample)


def _read(file_or_path, is_path=False):
    if is_path:
        return pd.read_excel(file_or_path)
    if file_or_path.name.endswith(".csv"):
        return pd.read_csv(file_or_path)
    return pd.read_excel(file_or_path)


@st.cache_data
def load_sample():
    sales = pd.read_excel("sample_data/sales_history_SAMPLE.xlsx")
    inventory = pd.read_excel("sample_data/inventory_by_region_SAMPLE.xlsx")
    invoices = pd.read_excel("sample_data/shipment_invoices_SAMPLE.xlsx")
    return sales, inventory, invoices


sales_df = inventory_df = invoices_df = None
data_ready = False

if use_sample:
    sales_df, inventory_df, invoices_df = load_sample()
    data_ready = True
else:
    if sales_file and inventory_file and invoices_file:
        try:
            sales_df = _read(sales_file)
            inventory_df = _read(inventory_file)
            invoices_df = _read(invoices_file)
            data_ready = True
        except Exception as e:
            st.sidebar.error(f"Couldn't read one of the files: {e}")
    else:
        st.sidebar.info("Upload all 3 files, or check 'Use sample data' to explore the tool.")

st.sidebar.markdown("### 2. Demand Window")
window_days = st.sidebar.slider("Trailing days of sales history", 30, 180, 90, step=15)

st.sidebar.markdown("### 3. Placement Fee Schedule ($/unit)")
st.sidebar.caption("Editable — verify against current Seller Central rates. Amazon revises these periodically.")

if "fee_schedule" not in st.session_state:
    st.session_state.fee_schedule = {
        k: dict(v) for k, v in cost_model.DEFAULT_PLACEMENT_FEE_SCHEDULE.items()
    }

with st.sidebar.expander("Edit fee schedule", expanded=False):
    for tier in st.session_state.fee_schedule:
        st.markdown(f"**{tier}**")
        c1, c2, c3 = st.columns(3)
        st.session_state.fee_schedule[tier]["1_location"] = c1.number_input(
            "1 loc", value=float(st.session_state.fee_schedule[tier]["1_location"]),
            key=f"{tier}_1loc", step=0.05, format="%.2f", label_visibility="collapsed"
        )
        st.session_state.fee_schedule[tier]["2-4_locations"] = c2.number_input(
            "2-4 loc", value=float(st.session_state.fee_schedule[tier]["2-4_locations"]),
            key=f"{tier}_24loc", step=0.05, format="%.2f", label_visibility="collapsed"
        )
        st.session_state.fee_schedule[tier]["5+_locations"] = c3.number_input(
            "5+ loc", value=float(st.session_state.fee_schedule[tier]["5+_locations"]),
            key=f"{tier}_5loc", step=0.05, format="%.2f", label_visibility="collapsed"
        )

st.sidebar.markdown("### 4. Demand Basis")
use_corrected = st.sidebar.toggle(
    "Use sell-through-corrected demand (recommended)", value=True,
    help="OFF uses raw historical unit volume, which can create a feedback loop: regions that were "
         "overstocked look like 'high demand' even if they're just slow-moving. ON corrects for this "
         "using sell-through velocity (units sold relative to units available)."
)

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
st.title("Master Shipment Intelligence Tool")
st.caption(
    "Demand-weighted regional placement recommendations, with full cost transparency. "
    "This tool recommends — it does not auto-create shipments in Seller Central."
)

if not data_ready:
    st.warning("Waiting on data. Upload all 3 files in the sidebar, or enable sample data to explore.")
    st.stop()

# Column mapping assumptions (sample + expected real schema use the same names;
# for a real upload with different headers, surface a mapping step).
expected_sales_cols = {"Order Date", "SKU", "ASIN", "Region", "Quantity"}
expected_inv_cols = {"SKU", "Region", "On-Hand Units"}
expected_inv_cols_fc = {"FC Code"}
expected_invoice_cols = {"Destination Region", "Total Units", "Total Weight (lb)", "Invoice Total ($)"}

missing_sales = expected_sales_cols - set(sales_df.columns)
missing_inv = expected_inv_cols - set(inventory_df.columns)
missing_invoice = expected_invoice_cols - set(invoices_df.columns)

if missing_sales or missing_inv or missing_invoice:
    st.error(
        "Some expected columns weren't found. This version expects: \n\n"
        f"- Sales History: {sorted(expected_sales_cols)} (missing: {sorted(missing_sales) or 'none'})\n"
        f"- Inventory: {sorted(expected_inv_cols)} (missing: {sorted(missing_inv) or 'none'})\n"
        f"- Invoices: {sorted(expected_invoice_cols)} (missing: {sorted(missing_invoice) or 'none'})\n\n"
        "Rename columns to match, or let me know and I'll add a column-mapping step for your exact export format."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Compute engine outputs (recalculates live on any input change)
# ---------------------------------------------------------------------------
demand_profile = demand_engine.compute_demand_profile(sales_df, inventory_df, window_days=window_days)
freight_rates = cost_model.derive_freight_rate_per_lb(invoices_df)
as_of_date = demand_profile.attrs.get("as_of_date", "—")

pct_basis_suffix = "corrected" if use_corrected else "raw"

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_dash, tab_recommend, tab_export = st.tabs(["📊 Dashboard", "🎯 Recommendation", "📁 Export"])

# ============================ DASHBOARD TAB ===============================
with tab_dash:
    col1, col2, col3 = st.columns(3)
    total_units_sold = sum(demand_profile[f"{r}_units_sold"].sum() for r in REGIONS)
    total_on_hand = sum(demand_profile[f"{r}_on_hand"].sum() for r in REGIONS)
    east_share_current = demand_profile["East_on_hand"].sum() / total_on_hand if total_on_hand else 0

    col1.metric("Units Sold (window)", f"{int(total_units_sold):,}")
    col2.metric("Current On-Hand", f"{int(total_on_hand):,}")
    col3.metric("Current East Inventory Share", f"{east_share_current*100:.0f}%",
                help="Your stated status quo: majority of inventory sits in East today.")

    st.markdown("#### Regional Demand vs. Current Inventory Allocation")
    st.caption(
        f"Demand basis: {'sell-through-corrected (velocity-weighted)' if use_corrected else 'raw unit volume'}. "
        "If a region's demand bar is taller than its inventory bar, that region is likely under-stocked "
        "relative to where it's actually selling."
    )

    agg_demand = {r: demand_profile[f"{r}_demand_pct_{pct_basis_suffix}"].mean() for r in REGIONS}
    agg_inventory_share = {r: demand_profile[f"{r}_on_hand"].sum() / total_on_hand if total_on_hand else 0 for r in REGIONS}

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Demand Share", x=REGIONS, y=[agg_demand[r]*100 for r in REGIONS],
        marker_color=ORANGE, text=[f"{agg_demand[r]*100:.0f}%" for r in REGIONS], textposition="outside"
    ))
    fig.add_trace(go.Bar(
        name="Current Inventory Share", x=REGIONS, y=[agg_inventory_share[r]*100 for r in REGIONS],
        marker_color=GREY, text=[f"{agg_inventory_share[r]*100:.0f}%" for r in REGIONS], textposition="outside"
    ))
    fig.update_layout(
        barmode="group", height=380, plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Georgia, serif", color=CHARCOAL),
        yaxis_title="% share", legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=40, b=20, l=40, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Per-SKU Demand Profile")
    display_cols = ["SKU"] + [f"{r}_demand_pct_{pct_basis_suffix}" for r in REGIONS]
    profile_display = demand_profile[display_cols].copy()
    for r in REGIONS:
        profile_display[f"{r}_demand_pct_{pct_basis_suffix}"] = (profile_display[f"{r}_demand_pct_{pct_basis_suffix}"] * 100).round(1)
    profile_display.columns = ["SKU"] + [f"{r} Demand %" for r in REGIONS]
    st.dataframe(profile_display, use_container_width=True, hide_index=True)

    st.markdown("#### Freight Rate by Region (back-calculated from your invoices)")
    rate_display = freight_rates[["Region", "rate_per_lb", "rate_per_unit", "n_invoices"]].copy()
    rate_display.columns = ["Region", "$/lb", "$/unit", "Invoices Used"]
    rate_display["$/lb"] = rate_display["$/lb"].round(2)
    rate_display["$/unit"] = rate_display["$/unit"].round(2)
    st.dataframe(rate_display, use_container_width=True, hide_index=True)
    if (freight_rates["n_invoices"] == 0).any():
        st.caption("⚠️ Some regions have 0 invoices on record — their rate falls back to the average of "
                   "other regions. Treat that number as a rough placeholder, not a derived rate.")

# ============================ RECOMMENDATION TAB ===========================
with tab_recommend:
    st.markdown("#### Get a Recommendation for a Specific Shipment")

    sku_options = demand_profile["SKU"].tolist()
    selected_sku = st.selectbox("Select SKU", sku_options)
    total_units_input = st.number_input("Total units in this shipment", min_value=1, value=1000, step=50)

    c1, c2 = st.columns(2)
    size_tier = c1.selectbox("Size tier", list(st.session_state.fee_schedule.keys()), index=1)
    avg_unit_weight = c2.number_input("Avg unit weight (lb)", min_value=0.01, value=1.1, step=0.1)

    sku_row = demand_profile[demand_profile["SKU"] == selected_sku].iloc[0]
    if use_corrected:
        demand_pct = demand_engine.get_sku_demand_summary(sku_row)
    else:
        demand_pct = demand_engine.get_sku_demand_summary_raw(sku_row)

    result = decision_engine.recommend_split(
        total_units_input, demand_pct, freight_rates, size_tier, avg_unit_weight,
        fee_schedule=st.session_state.fee_schedule
    )

    st.markdown("##### Recommended Split")
    rcols = st.columns(3)
    for i, region in enumerate(REGIONS):
        units = result["demand_optimal"]["units"][region]
        pct = demand_pct.get(region, 0) * 100
        is_top = units == max(result["demand_optimal"]["units"].values())
        with rcols[i]:
            st.markdown(
                f"""<div style="background:{ORANGE if is_top else '#FFFFFF'};
                border:1px solid {'transparent' if is_top else '#D8DADD'}; border-radius:4px;
                padding:1rem; text-align:center;">
                <div style="color:{'white' if is_top else SLATE}; font-size:0.8rem; letter-spacing:1px;">{region.upper()}</div>
                <div style="color:{'white' if is_top else CHARCOAL}; font-size:2rem; font-weight:bold;">{units:,}</div>
                <div style="color:{'white' if is_top else GREY}; font-size:0.8rem;">{pct:.0f}% of demand</div>
                </div>""",
                unsafe_allow_html=True
            )

    st.markdown("##### Cost Tradeoff")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Recommended Split Cost", f"${result['demand_optimal']['cost']['total_cost']:,.2f}")
    cc2.metric(f"Cheapest Option ({result['cheapest']['region']} only)",
               f"${result['cheapest']['cost']['total_cost']:,.2f}")
    delta = result["cost_delta_vs_cheapest"]
    cc3.metric("Cost Delta", f"${abs(delta):,.2f} {'more' if delta > 0 else 'less' if delta < 0 else 'same'}",
               delta=f"{delta:,.2f}", delta_color="inverse")

    st.info(result["rationale"])

    st.session_state["_last_recommendation"] = {
        "sku": selected_sku, "region_split": result["demand_optimal"]["units"], "demand_pct": demand_pct,
        "recommended_cost": result["demand_optimal"]["cost"]["total_cost"],
        "cheapest_region": result["cheapest"]["region"],
        "cheapest_cost": result["cheapest"]["cost"]["total_cost"],
        "cost_delta": result["cost_delta_vs_cheapest"],
        "coverage_gap_pct": result["coverage_gap_pct"] * 100,
        "rationale": result["rationale"],
    }

# ============================ EXPORT TAB ===================================
with tab_export:
    st.markdown("#### Export Recommendations")
    st.caption("Generates fresh from current data and assumptions — not a static snapshot of an old run.")

    e1, e2 = st.columns(2)
    bulk_units = e1.number_input("Units to recommend per SKU (applies to all SKUs in export)",
                                  min_value=1, value=1000, step=50)
    bulk_size_tier = e2.selectbox("Size tier (applies to all SKUs)", list(st.session_state.fee_schedule.keys()),
                                   index=1, key="bulk_tier")
    bulk_weight = st.number_input("Avg unit weight (lb, applies to all SKUs)", min_value=0.01, value=1.1, step=0.1,
                                   key="bulk_weight")

    sku_units_map = {sku: bulk_units for sku in demand_profile["SKU"].tolist()}
    rec_table = decision_engine.build_recommendation_table(
        demand_profile, freight_rates, bulk_size_tier, bulk_weight, sku_units_map,
        fee_schedule=st.session_state.fee_schedule
    )

    st.dataframe(rec_table, use_container_width=True, hide_index=True)

    wb = excel_export.build_workbook(
        rec_table, demand_profile, freight_rates, st.session_state.fee_schedule,
        window_days, as_of_date, sku_filter_label="All SKUs (pilot category)"
    )
    excel_bytes = excel_export.workbook_to_bytes(wb)

    st.download_button(
        "⬇️ Download Excel Workbook (Summary + Full Detail)",
        data=excel_bytes,
        file_name=f"shipment_intelligence_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("---")
    st.markdown("#### Export PowerPoint Snapshot")
    st.caption("2-slide snapshot for the SKU currently selected in the Recommendation tab.")

    if "_last_recommendation" not in st.session_state:
        st.warning("Go to the Recommendation tab and select a SKU first.")
    else:
        snap = st.session_state["_last_recommendation"]
        pptx_bytes = pptx_export.build_snapshot(
            sku_label=snap["sku"], region_split=snap["region_split"], demand_pct=snap["demand_pct"],
            recommended_cost=snap["recommended_cost"], cheapest_region=snap["cheapest_region"],
            cheapest_cost=snap["cheapest_cost"], cost_delta=snap["cost_delta"],
            coverage_gap_pct=snap["coverage_gap_pct"], rationale=snap["rationale"],
            window_days=window_days, as_of_date=as_of_date,
        )
        st.download_button(
            f"⬇️ Download PowerPoint Snapshot — {snap['sku']}",
            data=pptx_bytes,
            file_name=f"shipment_snapshot_{snap['sku']}_{datetime.now().strftime('%Y%m%d')}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
