"""
Stochastic Linear Programming (SLP) for regional shipment splits.

The deterministic LP optimizer (lp_optimizer.py) treats demand% and freight
rates as fixed, known numbers. That's a convenient fiction: a trailing
90-day window is one snapshot of demand that varies month to month (see
the regional-mix drift in generate_sample_data.py for a concrete example --
one SKU's West share swung from 46% to 63% across 15 months of the same
underlying "true" demand pattern).

This module instead:
  1. Builds multiple SCENARIOS from historical data -- each a separate
     trailing window's demand%, treated as one possible "draw" of what
     demand could look like.
  2. Solves a TWO-STAGE STOCHASTIC PROGRAM across those scenarios:
       - EXPECTED-COST mode: minimize the average cost across all scenarios
         (cheapest on average, accepts variance month to month)
       - WORST-CASE (robust) mode: minimize the maximum cost across all
         scenarios (costs a bit more on average, protects against the
         worst historical month recurring)

This is still a MILP under the hood (PuLP + CBC) -- "stochastic" describes
the PROBLEM FORMULATION (optimizing across multiple weighted scenarios
instead of one fixed input), not a different solver technology.
"""
import pulp
import numpy as np
import pandas as pd
from . import cost_model

REGIONS = ["East", "Central", "West"]


def build_demand_scenarios(sales_df, inventory_df, sku, window_days=90,
                            n_scenarios=6, sku_col="SKU", region_col="Region",
                            qty_col="Quantity", date_col="Order Date"):
    """
    Builds N scenarios of demand% for one SKU by computing sell-through-
    corrected demand over N different trailing windows, spaced across the
    available history -- e.g. the trailing 90 days as of 6 different
    historical "as of" dates, roughly one per month if you have 6+ months
    of data.

    Returns a list of dicts: [{"East": pct, "Central": pct, "West": pct,
    "window_end": date, "weight": 1/n_scenarios}, ...]

    If there isn't enough history for n_scenarios distinct non-degenerate
    windows, returns as many as the data supports and flags this via the
    'n_scenarios_actual' vs requested count -- callers should check this
    rather than assume they got what they asked for.
    """
    from . import demand_engine

    df = sales_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    sku_df = df[df[sku_col] == sku]

    if len(sku_df) == 0:
        return [], 0

    earliest = sku_df[date_col].min()
    latest = sku_df[date_col].max()
    total_span_days = (latest - earliest).days

    if total_span_days < window_days:
        # Not enough history for even one full window beyond the minimum --
        # fall back to a single scenario using all available data.
        as_of_dates = [latest]
    else:
        # Space scenario "as of" dates evenly across the available history,
        # each at least window_days apart from the start so each window is
        # a real (mostly non-overlapping) trailing slice, not the same data
        # sliced redundantly.
        usable_span = total_span_days - window_days
        if usable_span <= 0:
            as_of_dates = [latest]
        else:
            step = usable_span / max(1, n_scenarios - 1) if n_scenarios > 1 else usable_span
            as_of_dates = [
                earliest + pd.Timedelta(days=window_days) + pd.Timedelta(days=step * i)
                for i in range(n_scenarios)
            ]
            as_of_dates = sorted(set(as_of_dates))

    scenarios = []
    for as_of in as_of_dates:
        profile = demand_engine.compute_demand_profile(
            sales_df, inventory_df, window_days=window_days, as_of_date=as_of
        )
        sku_row = profile[profile[sku_col] == sku]
        if len(sku_row) == 0:
            continue
        sku_row = sku_row.iloc[0]
        demand_pct = {r: float(sku_row[f"{r}_demand_pct_corrected"]) for r in REGIONS}
        scenarios.append({**demand_pct, "window_end": as_of, "weight": None})

    n_actual = len(scenarios)
    if n_actual == 0:
        return [], 0

    # Equal-weight scenarios by default (no reason to believe any historical
    # window is more representative of the future than another, absent a
    # seasonality model telling us otherwise).
    for s in scenarios:
        s["weight"] = 1.0 / n_actual

    return scenarios, n_actual


def solve_stochastic_split(total_units, scenarios, freight_rates, size_tier,
                            avg_unit_weight_lb, fee_schedule=None, mode="expected",
                            regions=None):
    """
    Solves the two-stage stochastic program: ONE shipment split decision
    (made now, before demand is known) that performs well across all
    scenarios (each a possible realization of demand%).

    mode: "expected" minimizes the weighted-average cost across scenarios.
          "worst_case" minimizes the maximum cost across any single scenario
          (a minimax / robust formulation -- costs more on average but
          bounds the downside).

    Returns a dict with the chosen split, cost under each scenario, and
    summary stats (mean, max, min cost across scenarios) so the caller can
    show the actual spread, not just one number.
    """
    if regions is None:
        regions = REGIONS
    if fee_schedule is None:
        fee_schedule = cost_model.DEFAULT_PLACEMENT_FEE_SCHEDULE
    if not scenarios:
        raise ValueError("No scenarios provided -- need at least 1 historical window to optimize against.")

    tier_fees = fee_schedule.get(size_tier, fee_schedule["Large Standard"])
    rates = freight_rates.set_index("Region")["rate_per_lb"].to_dict()
    fallback_rate = np.nanmean([v for v in rates.values() if not np.isnan(v)]) if rates else 0.65

    prob = pulp.LpProblem("stochastic_split", pulp.LpMinimize)

    # FIRST-STAGE decision: the actual split, made once, before demand is
    # known -- this is what makes it "two-stage": one set of units[r]
    # variables shared across every scenario's cost calculation.
    units = {r: pulp.LpVariable(f"units_{r}", lowBound=0) for r in regions}
    used = {r: pulp.LpVariable(f"used_{r}", cat="Binary") for r in regions}

    M = total_units
    min_real_shipment = min(max(total_units * 0.01, 5), total_units / len(regions))
    for r in regions:
        prob += units[r] <= M * used[r]
        prob += units[r] >= min_real_shipment * used[r]

    prob += pulp.lpSum(units[r] for r in regions) == total_units

    n_used = pulp.lpSum(used[r] for r in regions)
    tier_1loc = pulp.LpVariable("tier_1loc", cat="Binary")
    tier_24loc = pulp.LpVariable("tier_24loc", cat="Binary")
    tier_5loc = pulp.LpVariable("tier_5loc", cat="Binary")
    prob += tier_1loc + tier_24loc + tier_5loc == 1
    prob += n_used <= 1 + len(regions) * (1 - tier_1loc)
    prob += n_used >= 1 * tier_1loc
    prob += n_used <= 4 + len(regions) * (1 - tier_24loc)
    prob += n_used >= 2 * tier_24loc - len(regions) * (1 - tier_24loc)
    prob += n_used >= 5 * tier_5loc

    fee_per_unit = (
        tier_fees["1_location"] * tier_1loc
        + tier_fees["2-4_locations"] * tier_24loc
        + tier_fees["5+_locations"] * tier_5loc
    )
    # Freight cost does NOT depend on demand scenario -- it only depends on
    # where units actually go, which is the same first-stage decision in
    # every scenario. What VARIES by scenario is how well that fixed split
    # matches each scenario's demand -- captured via a per-scenario
    # "coverage shortfall" penalty below, not via freight cost itself.
    freight_cost = pulp.lpSum(
        units[r] * avg_unit_weight_lb * rates.get(r, fallback_rate) for r in regions
    )
    placement_cost = fee_per_unit * total_units
    fixed_cost = freight_cost + placement_cost

    # SECOND-STAGE: a per-scenario "demand mismatch penalty" -- if scenario s
    # says region r should get demand_pct[s][r] of units but the first-stage
    # split under-serves that region relative to scenario s's demand, that's
    # a real cost (lost sales / stockout risk), modeled as a linear penalty
    # proportional to the shortfall. This is what makes scenarios matter --
    # without it, the optimizer would just pick the cheapest fixed split
    # and ignore demand variability entirely.
    PENALTY_PER_UNIT_SHORTFALL = max(rates.values()) * avg_unit_weight_lb * 3  # economically meaningful penalty
    scenario_costs = []
    shortfall_vars = []

    for s_idx, scenario in enumerate(scenarios):
        shortfalls = {}
        for r in regions:
            target = scenario.get(r, 0) * total_units
            shortfall = pulp.LpVariable(f"shortfall_{s_idx}_{r}", lowBound=0)
            # shortfall >= target - units[r]  (can't be negative, captured by lowBound=0)
            prob += shortfall >= target - units[r]
            shortfalls[r] = shortfall
        shortfall_vars.append(shortfalls)
        scenario_penalty = pulp.lpSum(shortfalls[r] for r in regions) * PENALTY_PER_UNIT_SHORTFALL
        scenario_costs.append(fixed_cost + scenario_penalty)

    if mode == "worst_case":
        max_cost = pulp.LpVariable("max_scenario_cost", lowBound=0)
        for sc in scenario_costs:
            prob += max_cost >= sc
        prob += max_cost
    else:
        weights = [s["weight"] for s in scenarios]
        expected_cost = pulp.lpSum(w * sc for w, sc in zip(weights, scenario_costs))
        prob += expected_cost

    solver = pulp.PULP_CBC_CMD(msg=0)
    prob.solve(solver)

    status = pulp.LpStatus[prob.status]
    is_optimal = status == "Optimal"

    if not is_optimal:
        return {
            "units": None, "is_optimal": False, "solver_status": status,
            "error": f"Stochastic solver failed (status: {status}).",
        }

    result_units = {r: int(round(units[r].varValue or 0)) for r in regions}
    diff = total_units - sum(result_units.values())
    if diff != 0:
        top_region = max(result_units, key=result_units.get)
        result_units[top_region] += diff

    # Compute the ACTUAL per-scenario shortfall for the chosen split -- this
    # is the real discriminating metric between modes. Freight+placement
    # cost is constant across scenarios (the split doesn't change), so
    # reporting it per-scenario would be misleading -- found via testing,
    # where expected-mode and worst-case-mode initially looked identical
    # per scenario because the wrong metric (a trivial 100%-by-construction
    # coverage check) was being surfaced instead of the actual shortfall
    # each scenario would experience under this fixed split.
    per_scenario_actual_cost = []
    fixed_cost_value = pulp.value(fixed_cost)
    cost_detail = cost_model.estimate_shipment_cost(
        result_units, freight_rates, size_tier, avg_unit_weight_lb, fee_schedule
    )

    for scenario in scenarios:
        shortfall_total = 0.0
        shortfall_by_region = {}
        for r in regions:
            target = scenario.get(r, 0) * total_units
            shortfall = max(0.0, target - result_units.get(r, 0))
            shortfall_by_region[r] = round(shortfall, 1)
            shortfall_total += shortfall

        # "Effective demand served" -- of THIS scenario's demand, what
        # fraction is actually met by the units allocated to each region
        # (capped at 100% per region; can't "over-serve" past the target)
        served_pct = 0.0
        for r in regions:
            target = scenario.get(r, 0) * total_units
            if target > 0:
                served_pct += scenario.get(r, 0) * min(1.0, result_units.get(r, 0) / target)

        per_scenario_actual_cost.append({
            "window_end": str(scenario.get("window_end", "")),
            "demand_pct": {r: scenario.get(r, 0) for r in regions},
            "fixed_cost": cost_detail["total_cost"],
            "unit_shortfall_total": round(shortfall_total, 1),
            "unit_shortfall_by_region": shortfall_by_region,
            "demand_served_pct": round(served_pct * 100, 1),
        })

    return {
        "units": result_units,
        "is_optimal": True,
        "solver_status": status,
        "mode": mode,
        "fixed_cost": round(fixed_cost_value, 2),
        "n_scenarios": len(scenarios),
        "per_scenario": per_scenario_actual_cost,
        "min_demand_served_pct": round(min(s["demand_served_pct"] for s in per_scenario_actual_cost), 1),
        "max_demand_served_pct": round(max(s["demand_served_pct"] for s in per_scenario_actual_cost), 1),
        "worst_case_unit_shortfall": round(max(s["unit_shortfall_total"] for s in per_scenario_actual_cost), 1),
    }


def compare_expected_vs_worst_case(total_units, scenarios, freight_rates, size_tier,
                                    avg_unit_weight_lb, fee_schedule=None):
    """
    Runs both modes and returns a side-by-side comparison so the user can
    see the actual tradeoff: how much more does the robust split cost, and
    how much better is its worst-case demand coverage.
    """
    expected_result = solve_stochastic_split(
        total_units, scenarios, freight_rates, size_tier, avg_unit_weight_lb,
        fee_schedule=fee_schedule, mode="expected"
    )
    worst_case_result = solve_stochastic_split(
        total_units, scenarios, freight_rates, size_tier, avg_unit_weight_lb,
        fee_schedule=fee_schedule, mode="worst_case"
    )
    return expected_result, worst_case_result
