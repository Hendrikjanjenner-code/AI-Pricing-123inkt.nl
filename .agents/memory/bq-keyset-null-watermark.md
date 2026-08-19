---
name: BQ keyset pagination & NULL watermarks
description: Keyset pagination on a nullable watermark column silently drops NULL rows.
---
Rule: when paginating on (watermark, pk), COALESCE the watermark to epoch in the WHERE, ORDER BY **and** in the last_key the caller builds — all three must agree, or NULL-watermark rows are skipped (or refetched forever).

**Why:** dev DB contained a dim_shop row with NULL created_at; `(CAST(wm),pk) > (:lk_wm,:lk_pk)` evaluates NULL and the row silently vanished from full syncs. Postgres sorts NULLs last by default, so the row is never reached.

**How to apply:** any keyset-paginated export over a nullable timestamp column.
