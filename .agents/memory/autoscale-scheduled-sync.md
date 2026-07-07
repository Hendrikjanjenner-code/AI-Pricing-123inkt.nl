---
name: Autoscale + heavy periodic jobs
description: Why in-process schedulers don't work on autoscale, and how PriceShape "last sync = never" was caused/fixed.
---

# In-process feed sync OOM-kills the deployment VM (206 MB feed)

**Rule:** The PriceShape feed is a ~206 MB JSON array. `_fetch_feed` loads it
whole (`resp.content`) and `json.loads` parses it entirely, ballooning to several
GB of RAM. Running that in-process on the web server (in-app `feed_sync_scheduler`
or a manual sync) OOM-kills a standard Reserved VM ~45 s after boot — the process
dies with NO crash log (SIGKILL signature), the app flaps "up ~1 min then not
live yet", and login fails only because the whole app is offline.

**Why:** Symptom was "published app keeps going down / can't log in". Health-check
`/api` fix made the app promote, but it then died on the first feed-sync cycle.

**How to apply:** Keep in-app sync OFF in the deployment (`DISABLE_FEED_SYNC=true`,
shared env) and run the 206 MB refresh out-of-process as a **Scheduled Deployment**
(`scheduled_sync.py`) on a machine with enough RAM (≈4–8 GB). Do NOT try to make a
small web VM parse the full feed in-request. A future memory-safe fix = streaming
parse (ijson) + chunked bulk insert instead of `json.loads` on the whole body.

# Autoscale can't run in-process background schedulers

**Rule:** Any recurring/background work that must run on a wall-clock schedule
(e.g. the PriceShape feed sync) will NOT run when the app is deployed as
*autoscale* — instances sleep between requests, so asyncio background tasks
started in the FastAPI lifespan never fire. A synchronous "manual sync" that
ingests ~500k rows also times out inside a single HTTP request.

**How to apply — two valid paths:**
1. **Reserved VM ("always on")**: publish as VM so the in-process
   `feed_sync_scheduler` stays alive and fires every `FEED_SYNC_INTERVAL`. One
   deployment, no extra script. The agent CANNOT set this: `.replit` edits are
   blocked and `deployConfig` is not exposed in the sandbox — the user picks
   "Reserved VM" in the Publishing UI.
2. **Scheduled Deployment** (keep web app on autoscale): run standalone
   `artifacts/api-server/scheduled_sync.py` cron-style as a separate deployment.

**Critical:** both the scheduler and the standalone script must run the FULL
refresh, not just the feed ingest. Feed ingest alone refreshes competitor prices
but leaves `sku_competition_score` (CI Dashboard) empty. The full order lives in
one shared helper `services/refresh.run_model_refresh`: ingest feed →
run_pricing_engine → feed_ingest.score_competition → feed_ingest.build_ai_matches
→ record ModelRun. Both paths call it so they stay identical.

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
