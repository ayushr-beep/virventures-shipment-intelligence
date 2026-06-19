# Master Shipment Intelligence Tool — Virventures

Demand-weighted FBA regional placement recommendations, with full cost
transparency. Built as a v1 pilot for one brand/category (sample data:
Tuffo rain suits) before rolling out further.

## What this does

- Reads your Sales History, Inventory-by-Region, and Shipment Invoices
- Computes a **sell-through-corrected** regional demand profile per SKU
  (not just raw sales volume — see "Why sell-through, not raw volume" below)
- Back-calculates your actual freight cost per region from invoice history
  (no guessed placeholder rates)
- Recommends a regional split per SKU, and shows the **dollar tradeoff**
  against the cheapest single-region option — explicitly, so a human makes
  the final call
- **Upload an actual Send to Amazon manifest** (the real "Create workflow"
  template you'd upload to Seller Central) and get a full shipment-level
  plan in one shot: every SKU on the manifest run through the same demand
  + cost engine, with a per-region breakdown and ready-to-use per-region
  manifest files to upload back to Amazon
- **Linear programming optimizer** (Recommendation tab → "Optimized" mode):
  finds the mathematically optimal regional split via a Mixed-Integer
  Linear Program, not just a proportional-allocation heuristic. Correctly
  models Amazon's placement fee as the step function it actually is
  (1 location = highest fee/unit, 2-4 = mid, 5+ = $0), and lets you slide
  a "minimum demand coverage required" threshold to see the real cost-vs-
  coverage Pareto frontier, not just two fixed comparison points
- **Stochastic optimizer** (Recommendation tab → "Stochastic" mode): the
  LP optimizer above assumes ONE fixed demand% (whatever your trailing
  window says right now). This mode instead builds several scenarios from
  different historical windows (e.g. ~6 months of trailing-90-day snapshots)
  and finds a split that performs well across ALL of them — either
  cheapest on average ("expected" mode) or safest against the worst
  historical month recurring ("worst case" / robust mode). Useful when
  demand genuinely varies month to month (seasonal products especially)
  and you don't want a recommendation built on one possibly-unrepresentative
  snapshot
- Exports: Excel workbook (summary + full detail tabs), PowerPoint snapshot
  (2 slides, for the SKU currently selected)

## What this does NOT do (by design, for v1)

- Does **not** connect live to Amazon SP-API — file upload only
- Does **not** auto-create shipments in Seller Central — this is a
  recommendation tool, execution stays manual
- Does **not** cover your full catalog — pilot scope is one brand/category
- Does **not** guarantee placement fee reduction on every shipment — Amazon's
  fee schedule is a step function (1 location = highest fee, 5+ locations =
  $0 fee), so chasing demand into 2-4 locations can sometimes cost MORE in
  fees even when it's right for sales. The tool shows you this tradeoff
  rather than hiding it.

## Why sell-through rate, not raw sales volume

If the demand model just said "ship more where it sold before," you'd create
a feedback loop: a region gets more inventory → it sells more (because it
has stock) → the model sees "high sales" and ships it even more → an
under-stocked region's sales stay low (because it has nothing to sell) →
the model reads that as "low demand" and starves it further. That's the
model manufacturing its own training data, not detecting real demand.

This tool corrects for that using **velocity**: units sold relative to
units available (sold + on-hand) in that region. A region that sold through
most of a small allocation is flagged as higher real demand than a region
that sold the same raw units off a much larger allocation. You can toggle
back to raw-volume basis in the sidebar to compare.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`.

### Deploying for the team (free)

Push this folder to a GitHub repo (private is fine) and deploy via
[Streamlit Community Cloud](https://streamlit.io/cloud) — free tier, no
infrastructure cost, matches the $0 budget. Point it at `app.py`.

## Expected file formats

Upload 3 separate files (.xlsx or .csv). Column names must match exactly,
or the app will tell you which are missing — there's no fuzzy column
mapping in v1.

**Sales History** — one row per order line:
| Order Date | SKU | ASIN | Region | Quantity |
|---|---|---|---|---|
| 2026-05-01 | TUFFO-RS-RED-M | B0RAINRD01 | East | 2 |

(`Region` should already be East/Central/West. If your export only has
state, map state→region before uploading — happy to add that mapping
logic if your real export comes in that shape.)

**Inventory by Region** — current on-hand snapshot:
| SKU | Region | On-Hand Units | FC Code (optional) |
|---|---|---|---|
| TUFFO-RS-RED-M | East | 850 | BWI1 |

**Shipment Invoices** — historical inbound shipment costs:
| Destination Region | Total Units | Total Weight (lb) | Invoice Total ($) |
|---|---|---|---|
| East | 600 | 660 | 410.40 |

## Editable assumptions (sidebar)

- **Demand window**: trailing 30–180 days
- **Placement fee schedule**: pre-filled with Amazon's published rates as
  of Jan 2026 (minimal split vs. 2-4 locations vs. 5+ locations, by size
  tier). Amazon has revised this schedule more than once in 2026 — **check
  current Seller Central rates periodically and update this table**, don't
  assume it stays accurate indefinitely.
- **Demand basis toggle**: sell-through-corrected (recommended) vs. raw
  volume, for comparison

## Project structure

```
app.py                      Streamlit app (UI + orchestration)
modules/
  demand_engine.py          Sell-through-corrected regional demand profile
  cost_model.py              Freight rate derivation + placement fee logic
  decision_engine.py         Proportional-split heuristic (fast, simple)
  lp_optimizer.py             Mixed-integer LP optimizer (provably optimal,
                               correctly models the fee step-function)
  stochastic_optimizer.py     Multi-scenario stochastic LP (expected-cost
                               and worst-case/robust modes)
  manifest_intelligence.py   Parses Send-to-Amazon manifests, builds shipment plans
  excel_export.py            Workbook generation
  pptx_export.py              2-slide snapshot generation
sample_data/                 Synthetic Tuffo rain suit data for testing
generate_sample_data.py      Regenerates sample_data/ if needed
```

## Using the Stochastic Optimizer

The "Stochastic" mode in the Recommendation tab needs enough sales history
to build multiple distinct, mostly-non-overlapping trailing windows —
practically, this means **at least 6 months of order-level sales history**
to get a meaningful number of scenarios (it'll still run with less, but
falls back to fewer scenarios and tells you so). If your real upload only
has 90 days of history, this mode will effectively just give you one
scenario, which isn't meaningfully different from the plain LP optimizer —
that's not a bug, it's an honest reflection of "there isn't enough history
yet to know how demand varies."

The sample data (`generate_sample_data.py`) was extended to span 14 months
with deliberate seasonal swings (rain suits sell more in spring) and
month-to-month regional-mix drift, specifically so this mode has something
real to demonstrate against. Regenerate it any time with:
```bash
python generate_sample_data.py
```

## Using the Manifest Upload feature

Go to the **Shipment Plan (Manifest Upload)** tab and upload the same
`.xlsx` file you'd otherwise upload to Seller Central's "Send to Amazon"
flow (the template with Merchant SKU + Quantity columns). The tool:

1. Auto-detects the header row (Amazon's template wraps it in instructional
   rows, so this isn't a plain row-0 header)
2. Matches each SKU against your uploaded sales history
3. **Flags any SKU with no sales history as "unmatched"** rather than
   guessing a split for it — there's no demand signal for a SKU the tool
   has never seen sell anywhere, so it's excluded from the recommendation
   and shown separately for you to handle manually
4. For matched SKUs, runs the same demand + cost engine as the
   Recommendation tab, for the whole manifest at once
5. Gives you both a summary view (one row per SKU) and a region-rows view
   (one row per SKU per region), plus downloadable CSVs in the exact same
   column layout as Amazon's template — pre-split by region, ready to
   upload back to Seller Central as separate regional shipments

## Honest scope note

This is a transparent, rules-based optimization tool (sell-through-weighted
demand split + back-calculated cost model), not a machine-learning system
and not a reverse-engineered copy of any competitor's platform. That's a
deliberate choice for a $0-budget v1: fully explainable to leadership,
no model training or hosting cost, and a real upgrade over manual
hours-long guesswork — without overclaiming what it matches.
