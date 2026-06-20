"""
LP Optimizer.

Replaces the proportional-allocation heuristic in decision_engine.py with
a real Mixed-Integer Linear Program (MILP) that finds the PROVABLY optimal
regional split given:

  - total units to ship
  - a minimum demand-coverage requirement (the floor you're willing to accept)
  - freight cost per region ($/lb, derived from invoices)
  - Amazon's placement fee, which is a STEP FUNCTION of the number of
    distinct regions used (1 location = highest fee/unit, 2-4 = mid,
    5+ = $0) -- this is why it's a MILP and not a plain LP: the fee
    tier depends on a discrete count, which needs binary "is region X
    used at all" variables, not just continuous allocation amounts.

Objective: minimize total landed cost (freight + placement fees)
Constraint: allocation must cover at least `min_coverage_pct` of total
            historical demand (the floor protecting against an
            all-cheapest-region-only solution that ignores demand)

This is solved with PuLP + the bundled CBC solver -- free, no license,
runs in milliseconds for a 3-region problem.
"""
import pulp
import numpy as np
import pandas as pd
from . import cost_model

REGIONS = ["East", "Central", "West"]


def optimize_split(total_units, demand_pct: dict, freight_rates, size_tier,
                    avg_unit_weight_lb, fee_schedule=None, min_coverage_pct=0.0,
                    regions=None):
    """
    Solves the MILP for the optimal regional split.

    min_coverage_pct: minimum fraction (0-1) of historical demand that must
        be served. 0 = pure cost minimization (may ship everything to one
        region regardless of demand). 1.0 = must serve every region with
        nonzero demand at least proportionally. A middle value (e.g. 0.7)
        lets the optimizer trade off cost against coverage explicitly,
        rather than the old heuristic's fixed proportional split.

    Returns a dict matching the shape decision_engine.recommend_split()
    expects downstream, plus 'solver_status' and 'is_optimal' for transparency
    -- if the solver can't find a provably optimal solution, the caller
    should know rather than silently trusting an approximate answer.
    """
    if regions is None:
        regions = REGIONS

    if fee_schedule is None:
        fee_schedule = cost_model.DEFAULT_PLACEMENT_FEE_SCHEDULE
    tier_fees = fee_schedule.get(size_tier, fee_schedule["Large Standard"])

    rates = freight_rates.set_index("Region")["rate_per_lb"].to_dict()
    fallback_rate = np.nanmean([v for v in rates.values() if not np.isnan(v)]) if rates else 0.65

    prob = pulp.LpProblem("regional_split", pulp.LpMinimize)

    # Decision variables: units shipped to each region (continuous, will be
    # near-integer since we round at the end -- treating as continuous keeps
    # the solve fast and avoids unnecessary integer-rounding artifacts)
    units = {r: pulp.LpVariable(f"units_{r}", lowBound=0) for r in regions}

    # Binary: is region r used at all (nonzero allocation)?
    used = {r: pulp.LpVariable(f"used_{r}", cat="Binary") for r in regions}

    # Big-M linking, BOTH DIRECTIONS:
    #   (a) units[r] can only be > 0 if used[r] == 1
    #   (b) used[r] can only be 1 if units[r] >= a MEANINGFUL minimum
    #       (not a tiny epsilon -- a continuous LP relaxation will happily
    #       ship 0.5 token units to a region purely to flip its "used" flag
    #       and claim a cheaper fee tier without actually serving that
    #       region in any real sense. The threshold must be large enough
    #       that "used" means "received a real shipment portion", e.g. at
    #       least 1% of the total shipment or a flat minimum, whichever is
    #       larger.)
    M = total_units
    # min_real_shipment only guards against the solver gaming the fee tier by
    # flagging a ZERO-DEMAND region as "used" with a token allocation. It must
    # NOT also apply to regions that already have an explicit demand-coverage
    # floor below (min_coverage_pct > 0 case) -- stacking both constraints on
    # the same region can jointly exceed total_units even when each is
    # individually reasonable (found via testing: 10 units split across 3
    # regions with both a coverage floor AND a real-shipment floor active
    # on every region summed to >10, making the problem infeasible even
    # though either constraint alone was satisfiable).
    min_real_shipment = min(max(total_units * 0.01, 5), total_units / len(regions))
    regions_with_coverage_floor = set()
    if min_coverage_pct > 0:
        for r in regions:
            if demand_pct.get(r, 0) > 0:
                regions_with_coverage_floor.add(r)

    for r in regions:
        prob += units[r] <= M * used[r]
        if r not in regions_with_coverage_floor:
            prob += units[r] >= min_real_shipment * used[r]

    # Total units constraint
    prob += pulp.lpSum(units[r] for r in regions) == total_units

    # Demand coverage constraint: total allocated to regions with nonzero
    # demand must cover at least min_coverage_pct of identified demand.
    # Implemented as: for each region, if min_coverage_pct > 0, encourage
    # proportional minimums via a soft floor -- units[r] >= coverage_floor[r]
    # whenever that region has demand. This avoids the solver dumping
    # everything into the cheapest region when coverage_pct > 0.
    if min_coverage_pct > 0:
        for r in regions:
            d_pct = demand_pct.get(r, 0)
            if d_pct > 0:
                floor = min_coverage_pct * d_pct * total_units
                prob += units[r] >= floor * used[r]
                # If there's a floor for this region, it must be used when
                # the floor is positive -- force used[r] = 1 in that case.
                if floor > 0:
                    prob += used[r] == 1

    # Number of distinct locations used -- determines which fee tier applies.
    # We model the 3 fee tiers as mutually exclusive binary choices and let
    # the solver pick the cheapest VALID one given how many regions end up used.
    n_used = pulp.lpSum(used[r] for r in regions)

    tier_1loc = pulp.LpVariable("tier_1loc", cat="Binary")
    tier_24loc = pulp.LpVariable("tier_24loc", cat="Binary")
    tier_5loc = pulp.LpVariable("tier_5loc", cat="Binary")
    prob += tier_1loc + tier_24loc + tier_5loc == 1

    # Only 3 regions are modeled here (East/Central/West), so "5+" locations
    # is never reachable with 3 regions -- but the tier structure stays
    # correct: with N=3 regions, the maximum achievable tier is "2-4 locations".
    # Tier selection must match actual n_used:
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

    freight_cost = pulp.lpSum(
        units[r] * avg_unit_weight_lb * rates.get(r, fallback_rate) for r in regions
    )
    placement_cost = fee_per_unit * total_units

    prob += freight_cost + placement_cost

    solver = pulp.PULP_CBC_CMD(msg=0)
    prob.solve(solver)

    status = pulp.LpStatus[prob.status]
    is_optimal = status == "Optimal"

    if not is_optimal:
        # Don't fabricate a units split from an infeasible/unbounded solve --
        # that would present a non-answer as if it were a real recommendation.
        # Caller is responsible for falling back (e.g. to the proportional
        # heuristic) and surfacing this to the user rather than hiding it.
        return {
            "units": None,
            "cost": None,
            "solver_status": status,
            "is_optimal": False,
            "min_coverage_pct_used": min_coverage_pct,
            "error": (
                f"Solver could not find a feasible solution (status: {status}). "
                f"This usually means min_coverage_pct is too strict for this "
                f"shipment size, or the minimum-real-shipment threshold conflicts "
                f"with a very small total_units. Try lowering min_coverage_pct."
            ),
        }

    result_units = {r: int(round(units[r].varValue or 0)) for r in regions}
    diff = total_units - sum(result_units.values())
    if diff != 0:
        top_region = max(result_units, key=result_units.get)
        result_units[top_region] += diff

    cost_detail = cost_model.estimate_shipment_cost(
        result_units, freight_rates, size_tier, avg_unit_weight_lb, fee_schedule
    )

    return {
        "units": result_units,
        "cost": cost_detail,
        "solver_status": status,
        "is_optimal": is_optimal,
        "min_coverage_pct_used": min_coverage_pct,
    }


def compare_coverage_tradeoff_curve(total_units, demand_pct, freight_rates, size_tier,
                                     avg_unit_weight_lb, fee_schedule=None,
                                     coverage_levels=(0.0, 0.25, 0.5, 0.75, 1.0)):
    """
    Solves the MILP at several coverage floors and returns the cost at each
    level -- this is the actual cost-vs-coverage tradeoff curve, letting a
    human see the full Pareto frontier instead of just two points (cheapest
    vs. proportional). More honest than the old single-comparison approach.
    """
    rows = []
    for level in coverage_levels:
        result = optimize_split(
            total_units, demand_pct, freight_rates, size_tier, avg_unit_weight_lb,
            fee_schedule=fee_schedule, min_coverage_pct=level
        )
        rows.append({
            "Min Coverage Required (%)": round(level * 100, 0),
            **{f"{r} Units": result["units"][r] for r in REGIONS},
            "Total Cost ($)": result["cost"]["total_cost"],
            "Locations Used": result["cost"]["n_locations"],
            "Solver Status": result["solver_status"],
        })
    return pd.DataFrame(rows)
