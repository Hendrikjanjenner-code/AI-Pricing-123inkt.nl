---
name: Autoscale + heavy periodic jobs
description: Why in-process schedulers don't work on autoscale, and how PriceShape "last sync = never" was caused/fixed.
---

# Autoscale can't run in-process background schedulers

**Rule:** Any recurring/background work that must run on a wall-clock schedule
(e.g. the PriceShape feed sync) will NOT run when the app is deployed as
*autoscale* — instances sleep between requests, so asyncio background tasks
started in the FastAPI lifespan never fire. A synchronous "manual sync" that
ingests ~500k rows also times out inside a single HTTP request.

**How to apply:** Run heavy periodic refreshes as a separate **Scheduled
Deployment** (cron-style, runs to completion, not request-bound) via a standalone
script (`artifacts/api-server/scheduled_sync.py`). Keep the web app on autoscale.
The full refresh order mirrors the model-run endpoint: ingest feed →
run_pricing_engine → feed_ingest.score_competition → feed_ingest.build_ai_matches.

# "Last sync = never" for env-only connectors

**Rule:** The connectors UI reads the last-sync timestamp ONLY from the DB row
`connector_config.last_synced_at`. A connector configured purely via an env var
(PriceShape via `PRICESHAPE_FEED_URL`) has no config row, so a successful sync
never recorded a timestamp and the UI always showed "nooit".

**Why:** The sync route had a `pass` branch for the env-only case.

**How to apply:** After a successful sync, upsert the timestamp with
`INSERT ... ON CONFLICT (connector_name) DO UPDATE` (helper
`touch_last_synced` in `routes/connectors.py`) so it works env-only AND is
race-safe.

# Concurrent sync safety

**Rule:** `feed_ingest.ingest_feed` does delete-then-insert of today's rows, so
two overlapping syncs (scheduled job + in-process autosync) can duplicate/corrupt
day rows. `_run_sync` now takes a PostgreSQL session advisory lock
(`pg_try_advisory_lock`) keyed per connector and returns `status="skipped"` if a
sync is already running. Callers must treat `"skipped"` as a non-error.
