"""
Cost Model.

Two cost components feed the Decision Engine:

1. FREIGHT COST -- back-calculated $/lb (or $/unit, if weight isn't reliable)
   per destination region from historical invoice data, rather than a
   guessed placeholder constant.

2. PLACEMENT FEE -- Amazon's inbound placement service fee, which is a
   STEP FUNCTION based on number of destination locations, not a simple
   per-region cost. As of Jan 15, 2026: minimal split (1 location) carries
   the highest per-unit fee; splitting across 5+ Amazon-recommended
   locations eliminates the fee entirely. Source: Amazon fee update
   announcements, Jan 2026 -- rates are EDITABLE in the app sidebar since
   Amazon revises these periodically and we don't want stale numbers
   silently driving recommendations.
"""
import pandas as pd
import numpy as np

REGIONS = ["East", "Central", "West"]

# Default placement fee schedule, $/unit, by size tier and number of
# destination locations in the shipment plan. Editable in-app.
# Source basis: Amazon inbound placement service fee structure, effective
# Jan 15, 2026 (minimal split vs Amazon-optimized split tiers).
DEFAULT_PLACEMENT_FEE_SCHEDULE = {
    "Small Standard":  {"1_location": 0.40, "2-4_locations": 0.20, "5+_locations": 0.00},
    "Large Standard":  {"1_location": 0.60, "2-4_locations": 0.30, "5+_locations": 0.00},
    "Small Bulky":     {"1_location": 1.20, "2-4_locations": 0.60, "5+_locations": 0.00},
    "Large Bulky":     {"1_location": 1.80, "2-4_locations": 0.90, "5+_locations": 0.00},
    "Extra-Large":     {"1_location": 2.30, "2-4_locations": 1.15, "5+_locations": 0.00},
}


def derive_freight_rate_per_lb(invoices_df, region_col="Destination Region",
                                weight_col="Total Weight (lb)", cost_col="Invoice Total ($)",
                                units_col="Total Units"):
    """
    Back-calculates a blended $/lb and $/unit freight rate per region from
    historical invoices. Returns a DataFrame: Region, rate_per_lb, rate_per_unit,
    n_invoices, total_weight, total_cost -- so the user can see exactly how
    the rate was derived, not just trust a black-box number.
    """
    df = invoices_df.copy()
    grouped = df.groupby(region_col).agg(
        total_cost=(cost_col, "sum"),
        total_weight=(weight_col, "sum"),
        total_units=(units_col, "sum"),
        n_invoices=(cost_col, "count"),
    ).reset_index().rename(columns={region_col: "Region"})

    grouped["rate_per_lb"] = grouped["total_cost"] / grouped["total_weight"].replace(0, np.nan)
    grouped["rate_per_unit"] = grouped["total_cost"] / grouped["total_units"].replace(0, np.nan)

    for r in REGIONS:
        if r not in grouped["Region"].values:
            fallback_rate = grouped["rate_per_lb"].mean() if len(grouped) else 0.65
            grouped = pd.concat([grouped, pd.DataFrame([{
                "Region": r, "total_cost": 0, "total_weight": 0, "total_units": 0,
                "n_invoices": 0, "rate_per_lb": fallback_rate, "rate_per_unit": np.nan,
            }])], ignore_index=True)

    return grouped.set_index("Region").reindex(REGIONS).reset_index()


def get_placement_fee(n_locations, size_tier, fee_schedule=None):
    """Returns $/unit placement fee given number of destination locations and size tier."""
    if fee_schedule is None:
        fee_schedule = DEFAULT_PLACEMENT_FEE_SCHEDULE
    tier_fees = fee_schedule.get(size_tier, fee_schedule["Large Standard"])
    if n_locations <= 1:
        return tier_fees["1_location"]
    elif n_locations <= 4:
        return tier_fees["2-4_locations"]
    else:
        return tier_fees["5+_locations"]


def estimate_shipment_cost(region_units: dict, freight_rates: pd.DataFrame, size_tier: str,
                            avg_unit_weight_lb: float, fee_schedule=None):
    """
    Given a proposed split {region: units}, estimate total cost:
      freight (per region, using derived $/lb rate * weight shipped to that region)
      + placement fee (based on number of NON-ZERO destination regions, applied per unit)

    Returns dict: total_freight, total_placement_fee, total_cost, n_locations, by_region detail.
    """
    rates = freight_rates.set_index("Region")["rate_per_lb"].to_dict()
    n_locations = sum(1 for v in region_units.values() if v > 0)
    fee_per_unit = get_placement_fee(n_locations, size_tier, fee_schedule)

    detail = {}
    total_freight = 0.0
    total_units = sum(region_units.values())

    for region, units in region_units.items():
        if units <= 0:
            detail[region] = {"units": 0, "weight_lb": 0.0, "freight_cost": 0.0}
            continue
        weight_lb = units * avg_unit_weight_lb
        rate = rates.get(region, np.nanmean(list(rates.values())))
        freight_cost = weight_lb * rate
        total_freight += freight_cost
        detail[region] = {"units": units, "weight_lb": round(weight_lb, 1), "freight_cost": round(freight_cost, 2)}

    total_placement_fee = fee_per_unit * total_units
    total_cost = total_freight + total_placement_fee

    return {
        "total_freight": round(total_freight, 2),
        "total_placement_fee": round(total_placement_fee, 2),
        "fee_per_unit": fee_per_unit,
        "n_locations": n_locations,
        "total_cost": round(total_cost, 2),
        "by_region": detail,
    }
