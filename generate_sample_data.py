"""
Generates realistic sample data matching the expected schema for the
Master Shipment Intelligence Tool. Used for development/testing and as
a template for the user's real data structure.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

np.random.seed(42)

REGIONS = ["East", "Central", "West"]
STATES_BY_REGION = {
    "East": ["NY", "FL", "GA", "NC", "PA", "MA", "NJ", "VA"],
    "Central": ["TX", "IL", "OH", "MI", "MO", "TN", "WI", "MN"],
    "West": ["CA", "WA", "OR", "AZ", "NV", "CO", "UT"],
}

SKUS = [
    {"sku": "TUFFO-RS-RED-M", "asin": "B0RAINRD01", "title": "Tuffo Kids Rain Suit - Red - Medium", "true_demand": {"East": 0.20, "Central": 0.25, "West": 0.55}},
    {"sku": "TUFFO-RS-BLU-M", "asin": "B0RAINBL02", "title": "Tuffo Kids Rain Suit - Blue - Medium", "true_demand": {"East": 0.45, "Central": 0.30, "West": 0.25}},
    {"sku": "TUFFO-RS-GRN-L", "asin": "B0RAINGR03", "title": "Tuffo Kids Rain Suit - Green - Large", "true_demand": {"East": 0.30, "Central": 0.40, "West": 0.30}},
    {"sku": "TUFFO-RS-YEL-S", "asin": "B0RAINYL04", "title": "Tuffo Kids Rain Suit - Yellow - Small", "true_demand": {"East": 0.15, "Central": 0.20, "West": 0.65}},
    {"sku": "TUFFO-RS-RED-L", "asin": "B0RAINRD05", "title": "Tuffo Kids Rain Suit - Red - Large", "true_demand": {"East": 0.35, "Central": 0.35, "West": 0.30}},
]

# Current on-hand inventory by region - deliberately East-heavy to match
# the stated status quo, and deliberately mismatched vs true_demand above
# so the sell-through-rate correction has something real to catch.
CURRENT_INVENTORY_SKEW = {"East": 0.65, "Central": 0.25, "West": 0.10}


def generate_sales_history(n_orders_per_month=350, n_months=14):
    """
    Order-level rows: SKU, ASIN, ship-to state, region, qty, order date.
    Spans n_months of history (default 14, ~enough for SLP scenario building),
    with two deliberate sources of real variation month to month -- not just
    random noise around one fixed number:

      1. SEASONAL VOLUME: rain suits sell more in spring (Mar-May) and a
         smaller secondary bump in autumn (Sep-Oct), less in mid-summer/winter.
      2. REGIONAL MIX DRIFT: each SKU's true regional demand split wobbles
         month to month (a real West-leaning SKU might be 55% West one month,
         62% the next) -- this is exactly the kind of variation a single
         90-day window hides, and what a stochastic/multi-scenario approach
         is built to capture.
    """
    rows = []
    today = datetime(2026, 6, 19)
    start = today - timedelta(days=30 * n_months)

    # Seasonal multiplier by calendar month (rain suit pattern: spring peak,
    # smaller autumn bump, quiet in deep summer/winter)
    seasonal_multiplier = {
        1: 0.6, 2: 0.8, 3: 1.5, 4: 1.8, 5: 1.6, 6: 1.0,
        7: 0.5, 8: 0.5, 9: 0.9, 10: 1.2, 11: 0.7, 12: 0.6,
    }

    for sku_info in SKUS:
        sku, asin, base_demand = sku_info["sku"], sku_info["asin"], sku_info["true_demand"]

        for month_offset in range(n_months):
            month_start = start + timedelta(days=30 * month_offset)
            calendar_month = month_start.month
            mult = seasonal_multiplier[calendar_month]
            n_this_month = max(5, int(n_orders_per_month * mult))

            # Regional mix drift: wobble each region's share by up to +/-8
            # percentage points this month, renormalized -- real variation,
            # not just resampling noise around a fixed number.
            wobble = {r: base_demand[r] + np.random.uniform(-0.08, 0.08) for r in REGIONS}
            wobble = {r: max(0.02, v) for r, v in wobble.items()}
            total = sum(wobble.values())
            month_demand = {r: v / total for r, v in wobble.items()}

            regions_drawn = np.random.choice(REGIONS, size=n_this_month, p=[month_demand[r] for r in REGIONS])

            for region in regions_drawn:
                state = np.random.choice(STATES_BY_REGION[region])
                day_in_month = np.random.randint(0, 30)
                order_date = month_start + timedelta(days=int(day_in_month))
                qty = np.random.choice([1, 1, 1, 2, 2, 3], p=[0.5, 0.2, 0.1, 0.1, 0.05, 0.05])
                rows.append({
                    "Order Date": order_date.strftime("%Y-%m-%d"),
                    "SKU": sku,
                    "ASIN": asin,
                    "Product Title": sku_info["title"],
                    "Ship-To State": state,
                    "Region": region,
                    "Quantity": qty,
                })

    df = pd.DataFrame(rows)
    return df.sort_values("Order Date").reset_index(drop=True)


def generate_inventory(sales_df):
    """Current on-hand inventory by SKU x Region - intentionally East-skewed."""
    rows = []
    for sku_info in SKUS:
        sku, asin = sku_info["sku"], sku_info["asin"]
        total_units = np.random.randint(1800, 3000)
        for region in REGIONS:
            units = int(total_units * CURRENT_INVENTORY_SKEW[region] * np.random.uniform(0.85, 1.15))
            rows.append({
                "SKU": sku,
                "ASIN": asin,
                "Region": region,
                "FC Code": {"East": "BWI1", "Central": "MDW2", "West": "ONT8"}[region],
                "On-Hand Units": units,
            })
    return pd.DataFrame(rows)


def generate_invoices(n_invoices=60):
    """Historical inbound shipment invoices: weight, units, destination region, total cost."""
    rows = []
    today = datetime(2026, 6, 19)
    # Rough true cost structure we're trying to recover: West costs more per lb
    # (longer haul from a Central/East-based 3PL), Central cheapest.
    true_rate_per_lb = {"East": 0.62, "Central": 0.51, "West": 0.81}

    for i in range(n_invoices):
        region = np.random.choice(REGIONS, p=[0.55, 0.25, 0.20])  # invoice history is also East-skewed
        days_ago = np.random.randint(0, 180)
        ship_date = today - timedelta(days=int(days_ago))
        units = np.random.randint(150, 1200)
        avg_unit_weight_lb = np.random.uniform(0.9, 1.4)  # rain suit ~1 lb
        weight_lb = round(units * avg_unit_weight_lb, 1)
        base_cost = weight_lb * true_rate_per_lb[region]
        noise = np.random.uniform(0.92, 1.08)
        total_cost = round(base_cost * noise, 2)
        rows.append({
            "Shipment ID": f"FBA{15000000 + i}",
            "Ship Date": ship_date.strftime("%Y-%m-%d"),
            "Destination Region": region,
            "FC Code": {"East": "BWI1", "Central": "MDW2", "West": "ONT8"}[region],
            "Total Units": units,
            "Total Weight (lb)": weight_lb,
            "Invoice Total ($)": total_cost,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    sales = generate_sales_history()
    inventory = generate_inventory(sales)
    invoices = generate_invoices()

    sales.to_excel("sample_data/sales_history_SAMPLE.xlsx", index=False)
    inventory.to_excel("sample_data/inventory_by_region_SAMPLE.xlsx", index=False)
    invoices.to_excel("sample_data/shipment_invoices_SAMPLE.xlsx", index=False)

    print("Sales rows:", len(sales))
    print("Inventory rows:", len(inventory))
    print("Invoice rows:", len(invoices))
    print(sales.head())
