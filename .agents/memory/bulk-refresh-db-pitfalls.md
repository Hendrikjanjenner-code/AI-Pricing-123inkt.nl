---
name: Bulk feed-refresh DB pitfalls (numpy repr + statement timeout)
description: Two non-obvious bugs that only surface when the model run inserts real-volume feed data, not the tiny seed set.
---

# numpy 2.x scalar repr leaks into SQL → schema "np" does not exist

**Rule:** Never pass raw numpy scalars (`np.float64`, `np.int64`, …) as bound
parameters to psycopg2. Coerce to native Python (`v.item()` when
`isinstance(v, np.generic)`) before any insert/update.

**Why:** psycopg2 has no adapter for numpy scalar types, so it falls back to
`repr()`. In **numpy 2.x** `repr(np.float64(6.49))` is `'np.float64(6.49)'`
(numpy <2 gave `'6.49'`), which gets embedded into the SQL text — Postgres reads
`np.float64` as `schema.function` and raises
`InvalidSchemaName: schema "np" does not exist`. Latent for years; the pinned
`numpy>=2.4` made it fire. Only surfaces on a real model run (pandas/sklearn
computations yield numpy scalars), never on tiny hand-built seed data.

**How to apply:** Sanitize the numeric fields of recommendation/score dicts in
`engine/pricing_engine.py` (and any future pandas→DB path) through a `_py()`
helper right before `bulk_insert_mappings`.

# Bulk refresh needs its own long statement-timeout session

**Rule:** The feed-sync / model-run does DELETE-then-INSERT of hundreds of
thousands of rows per day (competitor prices, recommendations). The global
request `statement_timeout` (4s, `DB_STATEMENT_TIMEOUT_MS`) is far too short and
cancels the per-day DELETE (`QueryCanceled: canceling statement due to statement
timeout`). Run bulk background work on a **separate** SQLAlchemy engine/session
with a long timeout, never on the request session.

**Why:** A single shared engine forces a trade-off: raise the timeout and a slow
user query can hang a request; keep it low and the sync dies. `SET
statement_timeout` on a pooled connection also leaks the long timeout to the next
request that reuses that connection.

**How to apply:** `database.py` exposes `BackgroundSessionLocal` bound to a
dedicated `background_engine` (small pool, `DB_BACKGROUND_STATEMENT_TIMEOUT_MS`
default 10 min). The scheduler (`feed_sync_scheduler`) and the manual
`POST /connectors/{name}/sync` endpoint both use it for the heavy ingest; the
tiny ImportJob audit insert still uses the normal request/`SessionLocal` engine.
Keep the 4s guard on request sessions intact.
