---
name: Test-shop teardown FK
description: Why deleting test shops fails intermittently in full-suite runs
---
Rule: any test fixture that creates a `DimShop` must also delete that shop's `cost_usage_records` rows in teardown.
**Why:** cost metering writes a usage row per API request per shop, so a shop created via the API accumulates FK-referencing rows as other tests run — the delete then fails only in full-suite runs, not standalone, which makes it look flaky.
**How to apply:** in module-scoped shop fixtures, delete CostUsageRecord (and IntelligenceSignal) rows for the shop before deleting the DimShop row.
