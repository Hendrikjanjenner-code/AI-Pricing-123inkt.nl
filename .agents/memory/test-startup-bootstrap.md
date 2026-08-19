---
name: Test-suite startup lifecycle
description: Bootstrap-once guard and scheduler flag mismatch that make/keep the suite fast and isolated
---
Two durable rules for the API test suite:

1. Expensive idempotent startup work (DDL/migrations/seeding) must stay behind the once-per-process guard in the lifespan; each test module boots its own TestClient, so anything outside the guard runs dozens of times per suite.
2. Disable flags must match what main.py actually reads: the in-app DQ scheduler reads DISABLE_DATA_QUALITY_SCAN while the standalone scan scheduler reads DISABLE_DQ_SCAN. conftest sets both. Any new scheduler needs its DISABLE_* flag added to conftest, or it fires mid-suite (90s startup delays are shorter than a full run) and mutates shared tables.

**Why:** repeated bootstraps once pushed the suite past 5 minutes on a full dev-DB, and a mis-named disable flag let a scheduler run mid-suite causing order-dependent failures only in full runs.

**How to apply:** when adding lifespan work or schedulers, check the guard and conftest flags in the same change.
