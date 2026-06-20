"""
Decision Engine.

Combines the Demand Profile (where does real demand live, sell-through
corrected) with the Cost Model (what does each placement option cost) to
produce a recommended split -- WITH the dollar tradeoff shown explicitly,
so a human makes the final call rather than trusting a black box.

This does NOT auto-create Amazon shipments. It outputs a recommendation
table. Execution stays manual by design (v1 scope).
"""
import numpy as np
import pandas as pd
from . import cost_model

REGIONS = ["East", "Central", "West"]


def recommend_split(total_units, demand_pct: dict, freight_rates, size_tier,
                     avg_unit_weight_lb, fee_schedule=None, min_unit_threshold=0):
    """
    Given total units to ship and a demand_pct dict (e.g. from
    get_sku_demand_summary), returns:
      - demand_optimal split (rounded units per region, proportional to demand)
      - cheapest_split (single cheapest region, the "minimal split" baseline)
      - cost for both
      - the dollar delta and a plain-language rationale

    min_unit_threshold: if a region's allocated units would fall below this,
    fold it into the next-largest region rather than shipping a token amount
    (avoids "ship 3 units to Central" busywork).
    """
    # --- Demand-optimal split ---
    demand_units = {r: int(round(total_units * demand_pct.get(r, 0))) for r in REGIONS}
    diff = total_units - sum(demand_units.values())
    if diff != 0:
        top_region = max(demand_pct, key=demand_pct.get)
        demand_units[top_region] += diff

    if min_unit_threshold > 0:
        small_regions = [r for r, u in demand_units.items() if 0 < u < min_unit_threshold]
        if small_regions:
            top_region = max(demand_units, key=demand_units.get)
            for r in small_regions:
                demand_units[top_region] += demand_units[r]
                demand_units[r] = 0

    demand_cost = cost_model.estimate_shipment_cost(
        demand_units, freight_rates, size_tier, avg_unit_weight_lb, fee_schedule
    )

    # --- Cheapest split: single region, lowest landed cost (freight + 1-location fee) ---
    rates = freight_rates.set_index("Region")["rate_per_lb"].to_dict()
    cheapest_region = min(rates, key=lambda r: rates.get(r, np.inf))
    cheapest_units = {r: (total_units if r == cheapest_region else 0) for r in REGIONS}
    cheapest_cost = cost_model.estimate_shipment_cost(
        cheapest_units, freight_rates, size_tier, avg_unit_weight_lb, fee_schedule
    )

    # --- Amazon-optimized 5-location split (zero placement fee baseline) ---
    optimized_units = {r: int(round(total_units / len(REGIONS))) for r in REGIONS}
    diff2 = total_units - sum(optimized_units.values())
    if diff2 != 0:
        first_region = REGIONS[0]
        optimized_units[first_region] += diff2
    optimized_cost = cost_model.estimate_shipment_cost(
        optimized_units, freight_rates, size_tier, avg_unit_weight_lb, fee_schedule
    )

    cost_delta_vs_cheapest = demand_cost["total_cost"] - cheapest_cost["total_cost"]

    # Coverage = share of TRUE historical demand actually served by each option.
    # Demand-optimal split serves demand everywhere it exists (always ~100% by
    # construction, since it allocates proportionally to all regions with demand).
    # The meaningful comparison is the CHEAPEST single-region option: how much
    # of true demand does it miss by only stocking one region?
    demand_coverage_pct = sum(
        demand_pct.get(r, 0) for r, u in demand_units.items() if u > 0
    )
    cheapest_coverage_pct = demand_pct.get(cheapest_region, 0)
    coverage_gap_pct = demand_coverage_pct - cheapest_coverage_pct

    rationale = _build_rationale(
        demand_units, cheapest_region, cost_delta_vs_cheapest,
        demand_coverage_pct, cheapest_coverage_pct, coverage_gap_pct
    )

    return {
        "demand_optimal": {"units": demand_units, "cost": demand_cost},
        "cheapest": {"units": cheapest_units, "cost": cheapest_cost, "region": cheapest_region},
        "amazon_optimized_5loc": {"units": optimized_units, "cost": optimized_cost},
        "cost_delta_vs_cheapest": round(cost_delta_vs_cheapest, 2),
        "demand_coverage_pct": demand_coverage_pct,
        "cheapest_coverage_pct": cheapest_coverage_pct,
        "coverage_gap_pct": coverage_gap_pct,
        "rationale": rationale,
    }


def _build_rationale(demand_units, cheapest_region, cost_delta, demand_coverage, cheapest_coverage, coverage_gap):
    active_regions = [r for r, u in demand_units.items() if u > 0]
    lines = []

    if len(active_regions) == 1 and active_regions[0] == cheapest_region:
        lines.append(
            f"Demand and cost agree: {cheapest_region} is both the dominant demand region "
            f"and the cheapest to ship to. No tradeoff here."
        )
    else:
        coverage_phrase = (
            f"shipping only to {cheapest_region} would capture an estimated "
            f"{cheapest_coverage*100:.0f}% of this SKU's historical demand, missing "
            f"~{coverage_gap*100:.0f} percentage points of demand sitting in other regions."
        )
        if cost_delta > 0:
            lines.append(
                f"Shipping by demand costs ${cost_delta:,.2f} more than the cheapest single-region "
                f"option ({cheapest_region} only), but {coverage_phrase}"
            )
        elif cost_delta < 0:
            lines.append(
                f"Shipping by demand is ${abs(cost_delta):,.2f} CHEAPER than the single-region option, "
                f"AND {coverage_phrase} This is a strict improvement -- no tradeoff."
            )
        else:
            lines.append(f"Shipping by demand costs the same as the cheapest option, but {coverage_phrase}")

    return " ".join(lines)


def build_recommendation_table(demand_profile_df, freight_rates, default_size_tier,
                                default_unit_weight, sku_total_units_map, sku_col="SKU",
                                fee_schedule=None):
    """
    Runs recommend_split for every SKU in the demand profile and returns a
    flat summary DataFrame suitable for display and Excel export.
    sku_total_units_map: {sku: total_units_to_ship} -- e.g. next PO quantities.
    """
    rows = []
    for _, row in demand_profile_df.iterrows():
        sku = row[sku_col]
        total_units = sku_total_units_map.get(sku)
        if not total_units:
            continue
        demand_pct = {r: float(row[f"{r}_demand_pct_corrected"]) for r in REGIONS}
        result = recommend_split(
            total_units, demand_pct, freight_rates, default_size_tier,
            default_unit_weight, fee_schedule
        )
        out_row = {"SKU": sku, "Total Units": total_units}
        for r in REGIONS:
            out_row[f"{r} Units (Recommended)"] = result["demand_optimal"]["units"][r]
            out_row[f"{r} Demand %"] = round(demand_pct.get(r, 0) * 100, 1)
        out_row["Recommended Total Cost ($)"] = result["demand_optimal"]["cost"]["total_cost"]
        out_row["Cheapest Option Region"] = result["cheapest"]["region"]
        out_row["Cheapest Option Cost ($)"] = result["cheapest"]["cost"]["total_cost"]
        out_row["Cost Delta vs Cheapest ($)"] = result["cost_delta_vs_cheapest"]
        out_row["Demand Missed If Cheapest-Only (%)"] = round(result["coverage_gap_pct"] * 100, 1)
        out_row["Rationale"] = result["rationale"]
        rows.append(out_row)

    return pd.DataFrame(rows)
