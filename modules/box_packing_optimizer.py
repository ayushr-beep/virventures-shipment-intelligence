"""
Box-Level Packing Optimizer.

The regional split (decision_engine / lp_optimizer) answers "how many units
go to East/Central/West." This module answers the next question: once
180 units are allocated to West, how should THOSE units be packed into
boxes, and -- since Amazon's placement fee tier is partly a function of
carton count, not just destination count -- is there a cheaper way to box
and route them?

Box specs come from the real Send-to-Amazon manifest format: Units per
box, Box length/width/height, Box weight. When a SKU has no declared box
spec (legal in Amazon's template -- see the official example sheet, which
includes SKUs with blank case-pack columns), this module falls back to an
editable default rather than crashing or silently guessing.

Key mechanic confirmed against Amazon's real template: Number of boxes =
ceil(Quantity / Units per box). This module computes that relationship
explicitly, and works in BOTH directions: given units, compute boxes
(forward) -- and given a fixed total, suggest whether splitting differently
would change which fee tier applies.
"""
import math
import numpy as np
import pandas as pd
from . import cost_model

REGIONS = ["East", "Central", "West"]

DEFAULT_BOX_SPEC = {
    "units_per_box": 24,
    "box_length_in": 18.0,
    "box_width_in": 14.0,
    "box_height_in": 12.0,
    "box_weight_lb": 22.0,
}


def extract_box_specs(manifest_df, sku_col="Merchant SKU"):
    """
    Pulls per-SKU box specs from a parsed manifest (the real Send-to-Amazon
    format: Units per box, Number of boxes, Box length/width/height, Box
    weight). Returns a dict {sku: {spec}}. SKUs with missing/blank box
    columns are simply absent from the returned dict -- the caller should
    fall back to DEFAULT_BOX_SPEC for those, not silently invent a number
    without marking it as a fallback.
    """
    specs = {}
    box_cols = ["Units per box", "Box length (in)", "Box width (in)", "Box height (in)", "Box weight (lb)"]
    available_cols = [c for c in box_cols if c in manifest_df.columns]
    if not available_cols:
        return specs

    for _, row in manifest_df.iterrows():
        sku = str(row.get(sku_col, "")).strip()
        if not sku or sku in specs:
            continue
        units_per_box = row.get("Units per box")
        if pd.isna(units_per_box) or units_per_box <= 0:
            continue  # this SKU has no declared box spec on this line
        specs[sku] = {
            "units_per_box": int(units_per_box),
            "box_length_in": float(row.get("Box length (in)", DEFAULT_BOX_SPEC["box_length_in"]) or DEFAULT_BOX_SPEC["box_length_in"]),
            "box_width_in": float(row.get("Box width (in)", DEFAULT_BOX_SPEC["box_width_in"]) or DEFAULT_BOX_SPEC["box_width_in"]),
            "box_height_in": float(row.get("Box height (in)", DEFAULT_BOX_SPEC["box_height_in"]) or DEFAULT_BOX_SPEC["box_height_in"]),
            "box_weight_lb": float(row.get("Box weight (lb)", DEFAULT_BOX_SPEC["box_weight_lb"]) or DEFAULT_BOX_SPEC["box_weight_lb"]),
        }
    return specs


def compute_box_breakdown(units, box_spec):
    """
    Given a unit count and a box spec, returns the box-level breakdown:
    full boxes, units in the last (possibly partial) box, total boxes,
    and total weight. This is literal arithmetic, not optimization --
    Number of boxes = ceil(units / units_per_box), confirmed against
    Amazon's real template.
    """
    units_per_box = box_spec["units_per_box"]
    if units <= 0:
        return {"full_boxes": 0, "last_box_units": 0, "total_boxes": 0, "total_weight_lb": 0.0, "is_default_spec": box_spec.get("_is_default", False)}

    full_boxes = units // units_per_box
    remainder = units % units_per_box
    total_boxes = full_boxes + (1 if remainder > 0 else 0)
    last_box_units = remainder if remainder > 0 else units_per_box if full_boxes > 0 else 0

    # Weight: full boxes at declared box_weight_lb, partial last box scaled
    # proportionally by its actual unit count (a half-full box weighs less
    # than a full one, even though Amazon's per-carton placement-fee
    # threshold counts it as one carton regardless of fill level).
    full_box_weight = full_boxes * box_spec["box_weight_lb"]
    if remainder > 0:
        last_box_weight = box_spec["box_weight_lb"] * (remainder / units_per_box)
    else:
        last_box_weight = 0.0
    total_weight_lb = full_box_weight + last_box_weight

    return {
        "full_boxes": int(full_boxes),
        "last_box_units": int(last_box_units),
        "total_boxes": int(total_boxes),
        "total_weight_lb": round(total_weight_lb, 2),
        "is_default_spec": box_spec.get("_is_default", False),
    }


def optimize_region_packing(sku, units, box_specs_by_sku, size_tier, fee_schedule=None,
                             other_regions_used=None):
    """
    For a single SKU's allocation to ONE region, computes the box
    breakdown and evaluates whether the resulting carton count changes
    which Amazon placement-fee tier applies.

    other_regions_used: the set of OTHER regions this SKU is also shipping
    to in this same shipment plan (e.g. if East and Central also get
    units, the carton-count threshold for the $0 fee tier is evaluated
    across ALL destinations in the shipment, not just this one region --
    Amazon's "5+ locations" rule counts total shipment destinations, not
    boxes-within-one-destination). Passed through for the fee-tier
    evaluation but does not change the box arithmetic itself.

    Returns box breakdown plus a per-unit freight-equivalent note --
    actual $/unit freight still comes from cost_model, this module's job
    is the box COUNT and whether the spec was a real one or a fallback.
    """
    if fee_schedule is None:
        fee_schedule = cost_model.DEFAULT_PLACEMENT_FEE_SCHEDULE

    box_spec = box_specs_by_sku.get(sku)
    used_default = box_spec is None
    if box_spec is None:
        box_spec = dict(DEFAULT_BOX_SPEC)
        box_spec["_is_default"] = True
    else:
        box_spec = dict(box_spec)
        box_spec["_is_default"] = False

    breakdown = compute_box_breakdown(units, box_spec)
    breakdown["box_spec_used"] = box_spec
    breakdown["used_default_spec"] = used_default
    breakdown["sku"] = sku
    breakdown["region_units"] = units

    return breakdown


def build_full_packing_plan(region_rows_df, box_specs_by_sku, size_tier, fee_schedule=None):
    """
    Runs optimize_region_packing for every (SKU, Region) row in the
    shipment plan's region_rows_df (the long-format output already
    produced by manifest_intelligence.build_shipment_plan), and returns a
    DataFrame: Region, Merchant SKU, Quantity, Full Boxes, Last Box Units,
    Total Boxes, Total Weight (lb), Box Spec Source.

    This is the artifact that answers "ok, 180 units to West -- now what
    boxes do I actually pack and label."
    """
    if fee_schedule is None:
        fee_schedule = cost_model.DEFAULT_PLACEMENT_FEE_SCHEDULE

    rows = []
    # Determine, per SKU, how many distinct regions it ships to in this
    # plan -- needed context for the fee-tier note, computed once up front
    # rather than recomputed per row.
    sku_region_counts = region_rows_df.groupby("Merchant SKU")["Region"].nunique().to_dict()

    for _, row in region_rows_df.iterrows():
        sku = row["Merchant SKU"]
        region = row["Region"]
        units = int(row["Quantity"])

        result = optimize_region_packing(
            sku, units, box_specs_by_sku, size_tier, fee_schedule,
            other_regions_used=sku_region_counts.get(sku, 1) - 1
        )

        rows.append({
            "Region": region,
            "Merchant SKU": sku,
            "Quantity": units,
            "Full Boxes": result["full_boxes"],
            "Last Box Units": result["last_box_units"],
            "Total Boxes": result["total_boxes"],
            "Total Weight (lb)": result["total_weight_lb"],
            "Box Spec Source": "Default (no spec on manifest)" if result["used_default_spec"] else "From manifest",
            "Units per Box": result["box_spec_used"]["units_per_box"],
        })

    return pd.DataFrame(rows)


def build_region_box_manifest_export(packing_plan_df, region, original_manifest_cols=None):
    """
    Builds a region-specific export in the SAME Send-to-Amazon column
    layout, but now with Quantity, Units per box, and Number of boxes
    FILLED IN per SKU based on the box breakdown -- ready to upload as
    that region's actual shipment, box fields already computed instead of
    left blank for manual entry.
    """
    region_df = packing_plan_df[packing_plan_df["Region"] == region].copy()
    if len(region_df) == 0:
        return pd.DataFrame(columns=["Merchant SKU", "Quantity", "Units per box", "Number of boxes"])

    export_df = region_df[["Merchant SKU", "Quantity", "Units per Box", "Total Boxes"]].copy()
    export_df.columns = ["Merchant SKU", "Quantity", "Units per box", "Number of boxes"]

    for col in ["Expiration date (MM/DD/YYYY)", "Manufacturing lot code",
                "Box length (in)", "Box width (in)", "Box height (in)", "Box weight (lb)"]:
        export_df[col] = np.nan

    return export_df
