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


def generate_sales_history(n_orders=4000, days_back=120):
    """Order-level rows: SKU, ASIN, ship-to state, region, qty, order date."""
    rows = []
    today = datetime(2026, 6, 19)

    for sku_info in SKUS:
        sku, asin, demand = sku_info["sku"], sku_info["asin"], sku_info["true_demand"]
        n = n_orders // len(SKUS)
        regions_drawn = np.random.choice(REGIONS, size=n, p=[demand[r] for r in REGIONS])

        for region in regions_drawn:
            state = np.random.choice(STATES_BY_REGION[region])
            days_ago = np.random.randint(0, days_back)
            order_date = today - timedelta(days=int(days_ago))
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
