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
