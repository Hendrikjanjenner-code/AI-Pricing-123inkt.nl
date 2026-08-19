---
name: Test-shop teardown FK
description: Why deleting test shops fails intermittently in full-suite runs
---
Rule: any test fixture that creates a `DimShop` must also delete that shop's `cost_usage_records` rows in teardown.
**Why:** cost metering writes a usage row per API request per shop, so a shop created via the API accumulates FK-referencing rows as other tests run — the delete then fails only in full-suite runs, not standalone, which makes it look flaky.
**How to apply:** in module-scoped shop fixtures, delete CostUsageRecord (and IntelligenceSignal) rows for the shop before deleting the DimShop row.

# Tests vs real feed data in the dev DB

After a real PriceShape sync the dev DB holds 3k+ products and ~68k competitor
prices. **Why:** many tests run engines over the whole DB or assume a near-empty
one — competition-intelligence module setup grows to ~100s (whole file >5 min),
and assertions relying on default page-1 lists or top-N signal/decision budgets
(MAX_PER_TYPE, MAX_DECISIONS_PER_RUN) get crowded out by real data.
**How to apply:** in tests, query lists with an `entity_id` filter instead of
scanning page 1; seed extreme values (e.g. price_index 9.99/0.01) to survive
top-N caps, or `patch.object` the cap; never assume "latest model run" is the
one the test created.

Decision-engine tests: the cleanest fix is a dedicated DimShop — the engine's
signal query, /api/decisions/run, list, detail-by-id and transition all accept
shop_id, so a private shop dodges the MAX_DECISIONS_PER_RUN severity-ranking
crowd-out entirely. Pass shop_id everywhere: detail-by-id and transition are
shop-scoped and return 404/`{"detail":...}` for the wrong scope (transition
takes shop_id in the JSON body, not as a query param).

Data-quality detections look at the most recent ImportJob per upload_type:
tests must make their synthetic job the newest (created_at = now), otherwise a
real dev-DB sync wins and the issue never fires.

## Isolated runs: never assume pre-existing rows or tables
Test setup must call Base.metadata.create_all(bind=engine) and create its own
DimShop rows instead of assuming shop id 1 exists — a hardcoded shop_id=1 fails
on a fresh/empty DB with "Shop 1 not found" or "relation dim_shop does not exist".
**Why:** modules must pass standalone (pytest tests/test_x.py), not only after
another module happened to create tables/shops.
