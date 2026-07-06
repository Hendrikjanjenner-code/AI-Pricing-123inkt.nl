---
name: PriceShape feed ingest & model-run refresh semantics
description: How the full-catalog feed load and same-day model reruns behave.
---

The PriceShape feed is a **full-catalog loader**, not a match-against-existing step:
the DB starts empty, so ingest must *create* products (`dim_product`), own prices
(`fact_price_daily`), competitor prices (`fact_competitor_price_daily`), plus
categories/strategy mappings. All products default to `strategy_type=COMPETITOR_INDEX`
because the user chose real-feed-only (no synthetic sales/inventory); that strategy
degrades gracefully with `avg_units=0`.

**Day-scoped refresh (delete-then-insert).** Both fact tables and recommendations are
keyed by `date` (facts also by `source`). Re-ingesting the same day deletes today's
rows first, then inserts.

**Model-run rerun rule:** `run_pricing_engine` deletes today's **pending**
recommendations and regenerates them, but **preserves** rows with a human decision
(`approval_status != 'pending'`) — those SKUs are skipped and counted as skipped.
**Why:** a rerun after a fresh feed sync must reflect new prices without wiping
analyst approvals/rejections. Do not revert to "skip all already-done SKUs" — that
made reruns no-ops.

**Model run does both:** `trigger_model_run` runs the engine *and* `score_competition`
(PCIS). Do **not** swallow scoring errors — let them propagate so the run is marked
`failed` with an error message instead of a silent `completed`.
