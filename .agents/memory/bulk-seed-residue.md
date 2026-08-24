---
name: Bulk-seed residue breekt data-quality tests
description: Interrupted test runs can leave 70k bulk fixture rows; MISSING_COMPETITOR/STOCK_DATA detections then silently never trigger.
---

The competition parameter-limit test seeds 70k products + fact rows server-side. If the run is killed mid-fixture (timeout, parallel validation), teardown never runs and the dev DB keeps 70k `<PFX>-B-%` products, assignments, fact rows, a bulk shop and node.

**Why:** coverage detections that compare global distinct counts get masked by orphan fact rows (skus no longer in dim_product); MISSING_COMPETITOR/STOCK_DATA now count products without any fact row directly (NOT EXISTS) — keep that pattern for new coverage detections. Fixture teardowns need SET statement_timeout='120s' or concurrent load cancels them, which is how residue gets created.

**How to apply:** when data-quality coverage tests fail mysteriously, check for residue: products with a `-B-` bulk prefix and orphan fact rows. The bulk fixture now self-heals: it deletes prior-run residue by the recognizable `CHF%-B-%` / `CHF%-bulk` patterns before seeding (per-run random PFX makes exact-prefix deletes useless). Keep that pre-seed cleanup pattern for any new crash-prone bulk fixtures. Also raise statement_timeout before bulk deletes.
