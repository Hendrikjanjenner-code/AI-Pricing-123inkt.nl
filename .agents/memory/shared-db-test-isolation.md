---
name: Shared-DB test isolation patterns
description: Patterns that keep api-server tests deterministic on the shared dev database.
---
Tests run against one shared Postgres dev DB; other modules/suites leave residue and defaults bite.
**Why:** repeated full-suite-only failures came from (1) "most recent job" semantics picking up leftover ImportJobs, (2) emitter top-N selection crowded out by real data, (3) rows relying on a `shop_id` column default of 1 getting wiped/missed by shop-scoped rebuilds from other tests.
**How to apply:** seed fact rows one day in the future when code selects on max(date); purge same-type residue rows in an autouse fixture when code uses most-recent-row semantics; ALWAYS set shop_id explicitly on seeded rows — never rely on the default-shop column default.
