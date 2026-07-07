---
name: Autoscale + heavy periodic jobs
description: Why in-process schedulers don't work on autoscale, and how PriceShape "last sync = never" was caused/fixed.
---

# In-process feed sync OOM-killed the VM — FIXED by streaming parse

**History:** The PriceShape feed is a ~206 MB JSON array. The old path
(`_fetch_feed` → `resp.content` + `json.loads`) parsed it whole, ballooning to
several GB and OOM-killing a 2 GB Reserved VM ~45 s after boot — process died
with NO crash log (SIGKILL), app flapped "up ~1 min then not live yet", login
failed only because the whole app was offline. This was worked around by
disabling in-app sync (`DISABLE_FEED_SYNC=true`).

**Now FIXED — in-app sync is re-enabled (`DISABLE_FEED_SYNC=false`).** The JSON
is parsed **streaming** with `ijson` via
`connectors.priceshape_connector.stream_json_records` (a `_StreamReader` adapts
httpx `iter_bytes` to a file-like `read()`; `ijson.items(reader, "item")` yields
one record at a time; `feed_ingest._normalize` consumes the iterator; chunked
bulk insert). Measured peak dropped from ~1.5–2.5 GB to ~1.1 GB for the full
refresh (feed parse alone ~0.3 GB) — fits a 2 GB VM, 4 GB is comfortable.

**How to apply / guardrails:**
- Only a **top-level JSON array** streams; anything else raises `NotStreamable`
  and `_read_feed` falls back to the unchanged buffered `_fetch_feed` +
  `_parse_content` (CSV/XML/object-wrapper). Keep that fallback.
- The content-provided path (bulk load from disk) is intentionally still buffered.
- The Scheduled-Deployment (`scheduled_sync.py`) path remains valid for autoscale;
  the streaming fix just makes the **in-process Reserved-VM** scheduler safe too.

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
