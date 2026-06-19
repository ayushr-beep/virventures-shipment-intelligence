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
  decision_engine.py         Combines demand + cost into recommendations
  excel_export.py            Workbook generation
  pptx_export.py              2-slide snapshot generation
sample_data/                 Synthetic Tuffo rain suit data for testing
generate_sample_data.py      Regenerates sample_data/ if needed
```

## Honest scope note

This is a transparent, rules-based optimization tool (sell-through-weighted
demand split + back-calculated cost model), not a machine-learning system
and not a reverse-engineered copy of any competitor's platform. That's a
deliberate choice for a $0-budget v1: fully explainable to leadership,
no model training or hosting cost, and a real upgrade over manual
hours-long guesswork — without overclaiming what it matches.
