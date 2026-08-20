---
name: Feed-sync advisory lock vs full-suite runs
description: Dev workflow startup sync holds the priceshape advisory lock and flakes sync tests during validation runs.
---

**Rule:** connector-sync tests fail with "Er draait al een synchronisatie … overgeslagen" whenever the dev API-server workflow is (re)started shortly before a full-suite run: its feed-sync scheduler kicks off a real sync ~45s after startup and holds the advisory lock for minutes.

**Why:** completion validation restarts workflows and then runs the suite against the same shared DB, so `_run_sync`-based tests get `status: skipped` instead of ok/error.

**How to apply:** dev environment sets `FEED_SYNC_STARTUP_DELAY=1800` so restarts don't immediately sync (interval syncs still run). If those tests flake again, check `pg_locks` for advisory locks and whether the workflow just restarted before blaming the tests.
