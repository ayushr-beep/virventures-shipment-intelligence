"""
Data Continuity Checker.

Multi-year sales history is valuable for seasonality modeling ONLY if it's
actually continuous and represents the same underlying products across
time. This module runs BEFORE any seasonality/trend decomposition touches
the data, and flags the failure modes that would otherwise corrupt a
seasonal model silently:

  1. TIMELINE GAPS -- missing months (common across multi-year exports
     spanning report-format changes, account migrations, etc.)
  2. SKU DISCONTINUITY -- a SKU that sells steadily, vanishes for a long
     stretch, then reappears -- likely a discontinued/relaunched product,
     not genuine seasonal dormancy. Blending pre- and post-gap data as one
     continuous seasonal pattern would be wrong.
  3. ANOMALOUS PERIODS -- months with sales far outside the normal range
     for that SKU (e.g. a COVID-era demand shock) that would distort a
     seasonal average if not flagged for the user to decide whether to
     exclude them.

This module produces a report for a human to read, not an automatic
"fix" -- continuity problems need a judgment call (was this SKU really
discontinued? was this month really anomalous?) that the data alone can't
make safely.
"""
import pandas as pd
import numpy as np


def check_timeline_continuity(sales_df, date_col="Order Date", expected_gap_days=35):
    """
    Checks for months with zero or near-zero order volume across the WHOLE
    dataset (not per-SKU) -- a sign of a reporting gap, not a real demand
    gap, since it's extremely unlikely every single SKU has zero sales in
    the same month unless something broke upstream (export issue, account
    migration, etc.).

    Returns a DataFrame of monthly totals, with a 'flag' column marking
    months that look anomalously low relative to neighbors.
    """
    df = sales_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df["YearMonth"] = df[date_col].dt.to_period("M")

    monthly = df.groupby("YearMonth").size().reset_index(name="order_count")
    monthly = monthly.sort_values("YearMonth").reset_index(drop=True)

    # Fill in any month that's entirely MISSING from the data (not just low)
    full_range = pd.period_range(monthly["YearMonth"].min(), monthly["YearMonth"].max(), freq="M")
    monthly = monthly.set_index("YearMonth").reindex(full_range, fill_value=0).reset_index()
    monthly.columns = ["YearMonth", "order_count"]

    median_count = monthly["order_count"].median()
    monthly["flag"] = monthly["order_count"] < median_count * 0.15  # less than 15% of typical = suspicious gap
    monthly["flag_reason"] = np.where(
        monthly["order_count"] == 0, "Zero orders -- likely a data/export gap, not real demand collapse",
        np.where(monthly["flag"], "Unusually low volume vs. surrounding months", "")
    )

    return monthly


def check_sku_continuity(sales_df, sku_col="SKU", date_col="Order Date", gap_threshold_months=4):
    """
    For each SKU, finds the months it actually has sales in, and flags any
    gap of `gap_threshold_months` or more consecutive months with zero
    sales for that SKU SANDWICHED between months where it did sell --
    i.e. it wasn't just discontinued at the end of the data (that's normal),
    it went quiet then came back, which usually means a relaunch, a
    variation/listing change, or a SKU being reused for a different product.

    Returns a DataFrame: SKU, first_active, last_active, n_gap_periods,
    longest_gap_months, recommendation.
    """
    df = sales_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df["YearMonth"] = df[date_col].dt.to_period("M")

    full_range = pd.period_range(df["YearMonth"].min(), df["YearMonth"].max(), freq="M")
    rows = []

    for sku, sku_df in df.groupby(sku_col):
        active_months = set(sku_df["YearMonth"].unique())
        first_active = min(active_months)
        last_active = max(active_months)

        # Only check for gaps WITHIN the SKU's active lifespan, not before
        # first sale or after last sale (those are normal launch/discontinue,
        # not a concerning gap).
        lifespan_months = [m for m in full_range if first_active <= m <= last_active]
        gap_run = 0
        longest_gap = 0
        n_gap_periods = 0
        in_gap = False

        for m in lifespan_months:
            if m not in active_months:
                gap_run += 1
                if not in_gap:
                    n_gap_periods += 1
                    in_gap = True
                longest_gap = max(longest_gap, gap_run)
            else:
                gap_run = 0
                in_gap = False

        recommendation = ""
        if longest_gap >= gap_threshold_months:
            recommendation = (
                f"Gap of {longest_gap} consecutive months with no sales, then sales resumed. "
                f"Verify this is the same product before treating pre/post-gap data as one "
                f"continuous seasonal history -- it may be a relisting, variation change, or "
                f"a different product reusing the SKU."
            )

        rows.append({
            "SKU": sku, "first_active": str(first_active), "last_active": str(last_active),
            "n_gap_periods": n_gap_periods, "longest_gap_months": longest_gap,
            "needs_review": longest_gap >= gap_threshold_months,
            "recommendation": recommendation,
        })

    return pd.DataFrame(rows).sort_values("longest_gap_months", ascending=False)


def check_anomalous_periods(sales_df, sku_col="SKU", date_col="Order Date", qty_col="Quantity",
                             z_threshold=2.5):
    """
    For each SKU, flags months where order volume is a statistical outlier
    relative to that SKU's own history (z-score based) -- catches things
    like a COVID-era demand shock, a viral spike, or a stockout-driven
    collapse, any of which would distort a seasonal average if blended in
    without the user knowing it's there.

    Returns a DataFrame: SKU, YearMonth, units, z_score, flag_reason.
    """
    df = sales_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df["YearMonth"] = df[date_col].dt.to_period("M")

    monthly_sku = df.groupby([sku_col, "YearMonth"])[qty_col].sum().reset_index()

    rows = []
    for sku, sku_df in monthly_sku.groupby(sku_col):
        if len(sku_df) < 4:
            continue  # not enough history per SKU to compute a meaningful z-score
        mean = sku_df[qty_col].mean()
        std = sku_df[qty_col].std()
        if std == 0 or np.isnan(std):
            continue
        sku_df = sku_df.copy()
        sku_df["z_score"] = (sku_df[qty_col] - mean) / std
        outliers = sku_df[sku_df["z_score"].abs() >= z_threshold]
        for _, row in outliers.iterrows():
            direction = "spike" if row["z_score"] > 0 else "collapse"
            rows.append({
                "SKU": sku, "YearMonth": str(row["YearMonth"]), "units": row[qty_col],
                "z_score": round(row["z_score"], 2),
                "flag_reason": f"Demand {direction} ({row['z_score']:+.1f} std devs from this SKU's own average)",
            })

    return pd.DataFrame(rows).sort_values("z_score", key=lambda s: s.abs(), ascending=False) if rows else pd.DataFrame(
        columns=["SKU", "YearMonth", "units", "z_score", "flag_reason"]
    )


def run_full_continuity_report(sales_df, sku_col="SKU", date_col="Order Date", qty_col="Quantity"):
    """
    Runs all three checks and returns a combined summary dict, meant to be
    shown to the user BEFORE any seasonality/trend model is built on this
    data -- surfacing problems for a human judgment call, not silently
    auto-correcting them.
    """
    timeline = check_timeline_continuity(sales_df, date_col=date_col)
    sku_gaps = check_sku_continuity(sales_df, sku_col=sku_col, date_col=date_col)
    anomalies = check_anomalous_periods(sales_df, sku_col=sku_col, date_col=date_col, qty_col=qty_col)

    n_timeline_flags = int(timeline["flag"].sum())
    n_sku_flags = int(sku_gaps["needs_review"].sum())
    n_anomalies = len(anomalies)

    total_span_months = len(timeline)
    is_ready_for_seasonality = (n_timeline_flags == 0) and (n_sku_flags == 0) and (total_span_months >= 24)

    summary = {
        "total_span_months": total_span_months,
        "n_timeline_gaps": n_timeline_flags,
        "n_skus_needing_review": n_sku_flags,
        "n_anomalous_periods": n_anomalies,
        "is_ready_for_seasonality_modeling": is_ready_for_seasonality,
        "timeline_detail": timeline,
        "sku_gap_detail": sku_gaps,
        "anomaly_detail": anomalies,
    }

    if not is_ready_for_seasonality:
        reasons = []
        if total_span_months < 24:
            reasons.append(f"only {total_span_months} months of history (need 24+ for reliable seasonality)")
        if n_timeline_flags > 0:
            reasons.append(f"{n_timeline_flags} month(s) with suspiciously low/zero volume across all SKUs")
        if n_sku_flags > 0:
            reasons.append(f"{n_sku_flags} SKU(s) with a gap pattern suggesting discontinuation/relaunch")
        summary["not_ready_reasons"] = reasons

    return summary
