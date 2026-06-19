import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

from modules import demand_engine, cost_model, decision_engine, excel_export, pptx_export, manifest_intelligence, lp_optimizer, stochastic_optimizer

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
tab_dash, tab_recommend, tab_manifest, tab_export = st.tabs(
    ["📊 Dashboard", "🎯 Recommendation", "📦 Shipment Plan (Manifest Upload)", "📁 Export"]
)

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

    st.markdown("#### Demand Split Matrix — Every SKU × Every Region")
    st.caption(
        "Each row is a SKU, each column a region, each cell its demand share. Darker orange = more "
        "demand concentrated there. Scan down a column to see which SKUs lean toward that region; "
        "scan across a row to see how concentrated or spread out one SKU's demand is."
    )

    matrix_cols = [f"{r}_demand_pct_{pct_basis_suffix}" for r in REGIONS]
    matrix_df = demand_profile[["SKU"] + matrix_cols].copy()
    matrix_df.columns = ["SKU"] + REGIONS
    for r in REGIONS:
        matrix_df[r] = (matrix_df[r] * 100).round(1)
    matrix_df = matrix_df.set_index("SKU")

    fig_matrix = go.Figure(data=go.Heatmap(
        z=matrix_df.values,
        x=REGIONS,
        y=matrix_df.index.tolist(),
        colorscale=[[0, "#FFFFFF"], [0.5, "#F0997B"], [1, "#993C1D"]],
        text=[[f"{v:.0f}%" for v in row] for row in matrix_df.values],
        texttemplate="%{text}",
        textfont=dict(size=13, family="Georgia, serif", color=CHARCOAL),
        colorbar=dict(title="Demand %", ticksuffix="%"),
        zmin=0, zmax=max(60, matrix_df.values.max()),
        hovertemplate="SKU: %{y}<br>Region: %{x}<br>Demand: %{z:.1f}%<extra></extra>",
    ))
    fig_matrix.update_layout(
        height=max(220, 60 + 38 * len(matrix_df)),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Georgia, serif", color=CHARCOAL),
        margin=dict(t=20, b=20, l=20, r=20),
        xaxis=dict(side="top"),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_matrix, use_container_width=True)

    with st.expander("View as plain table instead"):
        plain_table = matrix_df.reset_index()
        plain_table.columns = ["SKU"] + [f"{r} Demand %" for r in REGIONS]
        st.dataframe(plain_table, use_container_width=True, hide_index=True)

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

    engine_mode = st.radio(
        "Recommendation method",
        [
            "Quick heuristic (proportional split)",
            "Optimized (linear programming — provably minimal cost)",
            "Stochastic (accounts for demand uncertainty across history)",
        ],
        horizontal=True,
        help="The heuristic splits units proportionally to demand, then checks the cost. The LP optimizer "
             "searches every possible split to find the mathematically cheapest option for ONE assumed "
             "demand%. The stochastic optimizer builds several scenarios from your actual sales history "
             "(demand% as it looked in different historical months) and finds a split that performs well "
             "across all of them — either cheapest on average, or safest against the worst month."
    )

    if engine_mode.startswith("Stochastic"):
        st.markdown("##### Build Demand Scenarios from History")
        sc1, sc2 = st.columns(2)
        n_scenarios_requested = sc1.slider(
            "Number of historical scenarios to build", min_value=2, max_value=12, value=6,
            help="Each scenario is a separate trailing-90-day window taken at a different point in your "
                 "sales history — e.g. roughly one per month if you have 6+ months of data."
        )
        stoch_mode = sc2.radio(
            "Optimize for", ["Expected cost (cheapest on average)", "Worst case (safest against a bad month)"],
            help="Expected mode minimizes average cost across all scenarios. Worst-case mode minimizes "
                 "the maximum cost/shortfall across any single scenario — costs a bit more on average, "
                 "but bounds your downside if demand looks like your worst historical month."
        )

        scenarios, n_actual = stochastic_optimizer.build_demand_scenarios(
            sales_df, inventory_df, selected_sku, window_days=90, n_scenarios=n_scenarios_requested
        )

        if n_actual == 0:
            st.error(f"No sales history found for {selected_sku} — can't build scenarios.")
            st.stop()
        if n_actual < n_scenarios_requested:
            st.warning(
                f"Only {n_actual} distinct historical windows available (requested {n_scenarios_requested}) "
                f"— there isn't enough sales history to build more non-overlapping scenarios. Results are "
                f"still valid, just based on fewer data points than requested."
            )

        with st.expander(f"View the {n_actual} scenarios used"):
            scenario_display = pd.DataFrame([
                {"As-Of Date": str(s["window_end"])[:10],
                 "East %": round(s["East"]*100, 1), "Central %": round(s["Central"]*100, 1),
                 "West %": round(s["West"]*100, 1)}
                for s in scenarios
            ])
            st.dataframe(scenario_display, use_container_width=True, hide_index=True)

        mode_key = "worst_case" if stoch_mode.startswith("Worst") else "expected"
        stoch_result = stochastic_optimizer.solve_stochastic_split(
            total_units_input, scenarios, freight_rates, size_tier, avg_unit_weight,
            fee_schedule=st.session_state.fee_schedule, mode=mode_key
        )

        if not stoch_result["is_optimal"]:
            st.error(f"Stochastic solver failed: {stoch_result.get('error', 'unknown error')}")
            st.stop()

        st.markdown("##### Recommended Split (robust to demand uncertainty)")
        rcols = st.columns(3)
        for i, region in enumerate(REGIONS):
            units = stoch_result["units"][region]
            is_top = units == max(stoch_result["units"].values())
            with rcols[i]:
                st.markdown(
                    f"""<div style="background:{ORANGE if is_top else '#FFFFFF'};
                    border:1px solid {'transparent' if is_top else '#D8DADD'}; border-radius:4px;
                    padding:1rem; text-align:center;">
                    <div style="color:{'white' if is_top else SLATE}; font-size:0.8rem; letter-spacing:1px;">{region.upper()}</div>
                    <div style="color:{'white' if is_top else CHARCOAL}; font-size:2rem; font-weight:bold;">{units:,}</div>
                    </div>""",
                    unsafe_allow_html=True
                )

        st.markdown("##### Performance Across Historical Scenarios")
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Fixed Cost (freight + placement)", f"${stoch_result['fixed_cost']:,.2f}")
        cc2.metric("Demand Served — Worst Scenario", f"{stoch_result['min_demand_served_pct']:.1f}%")
        cc3.metric("Demand Served — Best Scenario", f"{stoch_result['max_demand_served_pct']:.1f}%")

        st.caption(
            f"Worst-case unit shortfall across all {n_actual} scenarios: "
            f"{stoch_result['worst_case_unit_shortfall']:.0f} units. This is the number 'worst case' "
            f"mode is directly minimizing — switch modes above to compare."
        )

        per_scenario_df = pd.DataFrame([
            {
                "Scenario (as of)": s["window_end"][:10],
                "East %": round(s["demand_pct"]["East"]*100, 1),
                "Central %": round(s["demand_pct"]["Central"]*100, 1),
                "West %": round(s["demand_pct"]["West"]*100, 1),
                "Unit Shortfall": s["unit_shortfall_total"],
                "Demand Served %": s["demand_served_pct"],
            }
            for s in stoch_result["per_scenario"]
        ])
        st.dataframe(per_scenario_df, use_container_width=True, hide_index=True)

        st.session_state["_last_recommendation"] = {
            "sku": selected_sku, "region_split": stoch_result["units"], "demand_pct": demand_pct,
            "recommended_cost": stoch_result["fixed_cost"],
            "cheapest_region": min(freight_rates.set_index("Region")["rate_per_lb"].to_dict(),
                                    key=lambda r: freight_rates.set_index("Region")["rate_per_lb"].to_dict()[r]),
            "cheapest_cost": stoch_result["fixed_cost"],
            "cost_delta": 0,
            "coverage_gap_pct": 100 - stoch_result["min_demand_served_pct"],
            "rationale": (
                f"Stochastic split ({mode_key} mode) across {n_actual} historical demand scenarios: "
                f"${stoch_result['fixed_cost']:,.2f} fixed cost, demand served ranges from "
                f"{stoch_result['min_demand_served_pct']:.1f}% (worst scenario) to "
                f"{stoch_result['max_demand_served_pct']:.1f}% (best scenario) depending on which "
                f"historical demand pattern actually recurs."
            ),
        }

    elif engine_mode.startswith("Optimized"):
        min_coverage_pct = st.slider(
            "Minimum demand coverage required (%)", min_value=0, max_value=100, value=100, step=5,
            help="0% = pure cost minimization, may ship everything to one region regardless of demand. "
                 "100% = every region with demand must receive a proportional share. Move this slider to "
                 "see the real cost-vs-coverage tradeoff, not just two fixed points."
        ) / 100.0

        lp_result = lp_optimizer.optimize_split(
            total_units_input, demand_pct, freight_rates, size_tier, avg_unit_weight,
            fee_schedule=st.session_state.fee_schedule, min_coverage_pct=min_coverage_pct
        )

        if not lp_result["is_optimal"]:
            st.error(
                f"The optimizer couldn't find a feasible solution at {min_coverage_pct*100:.0f}% coverage "
                f"for this shipment size. {lp_result.get('error', '')} Try lowering the coverage requirement."
            )
            st.stop()

        display_units = lp_result["units"]
        display_cost = lp_result["cost"]["total_cost"]
        display_n_locations = lp_result["cost"]["n_locations"]

        st.markdown("##### Optimized Split")
        rcols = st.columns(3)
        for i, region in enumerate(REGIONS):
            units = display_units[region]
            pct = demand_pct.get(region, 0) * 100
            is_top = units == max(display_units.values())
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

        st.caption(f"Uses {display_n_locations} location(s) — solver status: {lp_result['solver_status']}")

        st.markdown("##### Cost-vs-Coverage Tradeoff Curve")
        st.caption(
            "This is the actual Pareto frontier — every point is a provably optimal split AT that coverage "
            "level. Moving the slider above traces this exact curve, so you can see precisely what each "
            "percentage point of demand coverage costs."
        )
        curve_df = lp_optimizer.compare_coverage_tradeoff_curve(
            total_units_input, demand_pct, freight_rates, size_tier, avg_unit_weight,
            fee_schedule=st.session_state.fee_schedule
        )
        fig_curve = go.Figure()
        fig_curve.add_trace(go.Scatter(
            x=curve_df["Min Coverage Required (%)"], y=curve_df["Total Cost ($)"],
            mode="lines+markers", line=dict(color=ORANGE, width=2.5), marker=dict(size=8),
        ))
        fig_curve.add_trace(go.Scatter(
            x=[min_coverage_pct * 100], y=[display_cost],
            mode="markers", marker=dict(size=14, color=CHARCOAL, symbol="diamond"),
            name="Your current selection", showlegend=False,
        ))
        fig_curve.update_layout(
            height=320, plot_bgcolor="white", paper_bgcolor="white",
            font=dict(family="Georgia, serif", color=CHARCOAL),
            xaxis_title="Minimum demand coverage required (%)", yaxis_title="Total landed cost ($)",
            margin=dict(t=20, b=40, l=60, r=20),
        )
        st.plotly_chart(fig_curve, use_container_width=True)

        cheapest_region_lp = min(
            freight_rates.set_index("Region")["rate_per_lb"].to_dict(),
            key=lambda r: freight_rates.set_index("Region")["rate_per_lb"].to_dict()[r]
        )
        cheapest_cost_lp = curve_df.iloc[0]["Total Cost ($)"]
        cost_delta_lp = display_cost - cheapest_cost_lp

        # Real demand-coverage gap (percentage points of demand NOT served by
        # shipping only to the cheapest region) -- same definition used by the
        # heuristic path, NOT a cost ratio. Mixing these up would put a
        # misleading number in front of the person reading the export.
        demand_coverage_lp = sum(demand_pct.get(r, 0) for r, u in display_units.items() if u > 0)
        cheapest_coverage_lp = demand_pct.get(cheapest_region_lp, 0)
        coverage_gap_pct_lp = (demand_coverage_lp - cheapest_coverage_lp) * 100

        st.session_state["_last_recommendation"] = {
            "sku": selected_sku, "region_split": display_units, "demand_pct": demand_pct,
            "recommended_cost": display_cost,
            "cheapest_region": cheapest_region_lp,
            "cheapest_cost": cheapest_cost_lp,
            "cost_delta": cost_delta_lp,
            "coverage_gap_pct": coverage_gap_pct_lp,
            "rationale": (
                f"LP-optimized split at {min_coverage_pct*100:.0f}% minimum demand coverage: "
                f"${display_cost:,.2f} total landed cost using {display_n_locations} location(s). "
                f"At 0% coverage (pure cost minimization), the cheapest possible cost is "
                f"${cheapest_cost_lp:,.2f} -- the ${cost_delta_lp:,.2f} difference is the price of "
                f"covering demand outside {cheapest_region_lp}."
            ),
        }

    else:
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

# ============================ MANIFEST / SHIPMENT PLAN TAB ==================
with tab_manifest:
    st.markdown("#### Upload a Send to Amazon Manifest")
    st.caption(
        "Upload the actual manifest you'd send to Seller Central (the 'Create workflow' template, "
        "with Merchant SKU + Quantity columns). The tool reads every SKU on it and runs the same "
        "demand + cost engine used in the Recommendation tab — for the whole shipment at once."
    )

    manifest_file = st.file_uploader("Send to Amazon manifest (.xlsx)", type=["xlsx"], key="manifest_upload")

    m1, m2 = st.columns(2)
    manifest_size_tier = m1.selectbox("Size tier (applies to all SKUs in this manifest)",
                                       list(st.session_state.fee_schedule.keys()), index=1, key="manifest_tier")
    manifest_weight = m2.number_input("Avg unit weight (lb, applies to all SKUs)", min_value=0.01,
                                       value=1.1, step=0.1, key="manifest_weight")

    if manifest_file is not None:
        try:
            parsed_manifest = manifest_intelligence.parse_manifest(manifest_file)
        except ValueError as e:
            st.error(str(e))
            parsed_manifest = None

        if parsed_manifest is not None:
            st.success(f"Read {len(parsed_manifest)} SKU lines from the manifest.")

            summary_df, region_rows_df, unmatched_df, totals = manifest_intelligence.build_shipment_plan(
                parsed_manifest, demand_profile, freight_rates, manifest_size_tier, manifest_weight,
                fee_schedule=st.session_state.fee_schedule
            )

            if totals["unmatched_skus"] > 0:
                st.warning(
                    f"⚠️ {totals['unmatched_skus']} of {len(parsed_manifest)} SKUs on this manifest have "
                    f"no sales history in your uploaded data — there's no demand signal for them, so they're "
                    f"excluded from the recommendation below. Review them in the 'Unmatched SKUs' section and "
                    f"either ship them by your existing process, or check the SKU spelling matches your sales data."
                )

            if len(summary_df) > 0:
                st.markdown("##### Shipment Totals")
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("SKUs Matched", f"{totals['total_skus']}")
                t2.metric("Total Units", f"{totals['total_units']:,}")
                t3.metric("Recommended Cost", f"${totals['total_recommended_cost']:,.2f}")
                delta = totals["total_cost_delta"]
                t4.metric("Cost Delta vs. Cheapest-Only",
                          f"${abs(delta):,.2f} {'more' if delta > 0 else 'less' if delta < 0 else 'same'}",
                          delta=f"{delta:,.2f}", delta_color="inverse")

                view_mode = st.radio(
                    "View", ["Summary (one row per SKU)", "Region rows (one row per SKU per region)"],
                    horizontal=True
                )

                if view_mode.startswith("Summary"):
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)
                else:
                    st.dataframe(region_rows_df, use_container_width=True, hide_index=True)

                st.markdown("##### Per-Region Send-to-Amazon Files")
                st.caption(
                    "Same column layout as the manifest you uploaded, pre-filled with the recommended "
                    "split for that region. Box/case-pack columns are left blank for you to fill in."
                )
                region_cols = st.columns(3)
                for i, region in enumerate(REGIONS):
                    region_export = manifest_intelligence.build_region_manifest_export(region_rows_df, region)
                    if len(region_export) == 0:
                        region_cols[i].caption(f"No units allocated to {region} in this shipment.")
                        continue
                    csv_bytes = region_export.to_csv(index=False).encode("utf-8")
                    region_cols[i].download_button(
                        f"⬇️ {region} ({region_export['Quantity'].sum()} units)",
                        data=csv_bytes,
                        file_name=f"manifest_{region.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        key=f"manifest_dl_{region}",
                    )

                st.session_state["_last_manifest_plan"] = {
                    "summary_df": summary_df, "region_rows_df": region_rows_df,
                    "unmatched_df": unmatched_df, "totals": totals,
                }
            else:
                st.info("No SKUs on this manifest matched your sales history — nothing to recommend yet.")

            if len(unmatched_df) > 0:
                with st.expander(f"Unmatched SKUs ({len(unmatched_df)}) — no sales history found"):
                    st.dataframe(unmatched_df, use_container_width=True, hide_index=True)
    else:
        st.info("Upload a manifest file to generate a shipment plan.")

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
    st.markdown("#### Export Manifest-Based Shipment Plan")
    st.caption("Full workbook for the manifest uploaded in the Shipment Plan tab — summary, region rows, and unmatched SKUs.")

    if "_last_manifest_plan" not in st.session_state:
        st.warning("Go to the Shipment Plan tab and upload a manifest first.")
    else:
        plan = st.session_state["_last_manifest_plan"]
        manifest_wb = excel_export.build_workbook(
            plan["summary_df"].rename(columns={"Merchant SKU": "SKU"}), demand_profile, freight_rates,
            st.session_state.fee_schedule, window_days, as_of_date,
            sku_filter_label="Uploaded manifest"
        )
        # Add the region-rows and unmatched-SKU detail as extra sheets
        from openpyxl.styles import Font
        ws_regions = manifest_wb.create_sheet("Region Rows (Long Format)")
        ws_regions.cell(row=1, column=1, value="One row per SKU per region — ready to filter into per-region uploads").font = Font(bold=True)
        for j, col in enumerate(plan["region_rows_df"].columns, start=1):
            ws_regions.cell(row=3, column=j, value=col).font = Font(bold=True)
        for i, (_, r) in enumerate(plan["region_rows_df"].iterrows()):
            for j, col in enumerate(plan["region_rows_df"].columns, start=1):
                ws_regions.cell(row=4 + i, column=j, value=r[col])

        if len(plan["unmatched_df"]) > 0:
            ws_unmatched = manifest_wb.create_sheet("Unmatched SKUs")
            ws_unmatched.cell(row=1, column=1, value="SKUs on the manifest with no sales history on record").font = Font(bold=True)
            for j, col in enumerate(plan["unmatched_df"].columns, start=1):
                ws_unmatched.cell(row=3, column=j, value=col).font = Font(bold=True)
            for i, (_, r) in enumerate(plan["unmatched_df"].iterrows()):
                for j, col in enumerate(plan["unmatched_df"].columns, start=1):
                    ws_unmatched.cell(row=4 + i, column=j, value=r[col])

        manifest_excel_bytes = excel_export.workbook_to_bytes(manifest_wb)
        st.download_button(
            "⬇️ Download Manifest Shipment Plan Workbook",
            data=manifest_excel_bytes,
            file_name=f"manifest_shipment_plan_{datetime.now().strftime('%Y%m%d')}.xlsx",
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
