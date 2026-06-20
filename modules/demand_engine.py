"""
Demand Profile Engine.

Computes, per SKU, the regional demand split using SELL-THROUGH RATE
(units sold / units available) rather than raw unit volume. This is the
anti-feedback-loop correction: a region that sold a lot because it was
overstocked is not the same as a region with genuine unmet demand.

velocity[region] = units_sold_in_window[region] / on_hand_inventory[region]

Regions with high velocity relative to their current stock are the ones
that would likely sell MORE if given more inventory -- that's the real
signal, not raw historical volume.
"""
import pandas as pd
import numpy as np

REGIONS = ["East", "Central", "West"]


def compute_demand_profile(sales_df, inventory_df, window_days=90, as_of_date=None,
                            sku_col="SKU", region_col="Region", qty_col="Quantity",
                            date_col="Order Date", inv_region_col="Region", inv_units_col="On-Hand Units"):
    """
    Returns a DataFrame indexed by SKU with columns:
      {region}_units_sold, {region}_on_hand, {region}_velocity,
      {region}_demand_pct_raw   (share of raw unit volume)
      {region}_demand_pct_corrected (share of sell-through velocity -- the recommended basis)
    """
    df = sales_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])

    if as_of_date is None:
        as_of_date = df[date_col].max()
    else:
        as_of_date = pd.to_datetime(as_of_date)

    window_start = as_of_date - pd.Timedelta(days=window_days)
    windowed = df[(df[date_col] > window_start) & (df[date_col] <= as_of_date)]

    sales_pivot = windowed.pivot_table(
        index=sku_col, columns=region_col, values=qty_col, aggfunc="sum", fill_value=0
    )
    for r in REGIONS:
        if r not in sales_pivot.columns:
            sales_pivot[r] = 0
    sales_pivot = sales_pivot[REGIONS]

    inv_pivot = inventory_df.pivot_table(
        index=sku_col, columns=inv_region_col, values=inv_units_col, aggfunc="sum", fill_value=0
    )
    for r in REGIONS:
        if r not in inv_pivot.columns:
            inv_pivot[r] = 0
    inv_pivot = inv_pivot[REGIONS]

    all_skus = sorted(set(sales_pivot.index) | set(inv_pivot.index))
    sales_pivot = sales_pivot.reindex(all_skus, fill_value=0)
    inv_pivot = inv_pivot.reindex(all_skus, fill_value=0)

    result = pd.DataFrame(index=all_skus)
    raw_total = sales_pivot.sum(axis=1).replace(0, np.nan)

    velocity = pd.DataFrame(index=all_skus, columns=REGIONS, dtype=float)
    for r in REGIONS:
        result[f"{r}_units_sold"] = sales_pivot[r]
        result[f"{r}_on_hand"] = inv_pivot[r]
        result[f"{r}_demand_pct_raw"] = (sales_pivot[r] / raw_total).fillna(1.0 / len(REGIONS))

        # velocity = sold / (sold + on_hand) -- a proxy for "how fast is this region
        # clearing what it's given." Using (sold + on_hand) rather than on_hand alone
        # avoids divide-by-zero when a region has 0 current stock, and still rewards
        # regions that sold well relative to what they had available in total.
        denom = (sales_pivot[r] + inv_pivot[r]).replace(0, np.nan)
        velocity[r] = (sales_pivot[r] / denom).fillna(0.0)

    velocity_total = velocity.sum(axis=1).replace(0, np.nan)
    for r in REGIONS:
        result[f"{r}_velocity"] = velocity[r]
        result[f"{r}_demand_pct_corrected"] = (velocity[r] / velocity_total)

    # Fallback: if a SKU has zero sales everywhere in the window (new SKU, or
    # all velocities are 0), fall back to equal split rather than NaN/zero split.
    corrected_cols = [f"{r}_demand_pct_corrected" for r in REGIONS]
    no_signal_mask = result[corrected_cols].sum(axis=1).fillna(0) == 0
    for r in REGIONS:
        result.loc[no_signal_mask, f"{r}_demand_pct_corrected"] = 1.0 / len(REGIONS)

    result = result.reset_index().rename(columns={"index": sku_col})
    result.attrs["window_days"] = window_days
    result.attrs["as_of_date"] = str(as_of_date.date())
    return result


def get_sku_demand_summary(profile_row, regions=REGIONS):
    """Helper: extract a clean {region: pct} dict from a profile row, corrected basis."""
    return {r: float(profile_row[f"{r}_demand_pct_corrected"]) for r in regions}


def get_sku_demand_summary_raw(profile_row, regions=REGIONS):
    """Helper: extract a clean {region: pct} dict from a profile row, raw-volume basis."""
    return {r: float(profile_row[f"{r}_demand_pct_raw"]) for r in regions}
