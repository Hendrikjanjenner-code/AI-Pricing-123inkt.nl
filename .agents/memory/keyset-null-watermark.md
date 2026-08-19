---
name: Keyset pagination vs NULL watermarks
description: BigQuery sync keyset pagination silently skips rows whose watermark column is NULL
---
Rule: keyset pagination on (watermark, pk) silently drops rows where the watermark column is NULL (SQL NULL comparisons), so watermark columns must never be NULL.

**Why:** a leftover dim_shop row with created_at NULL made the bq pagination regression test fail intermittently; the row simply vanished from the page stream.

**How to apply:** when tests or syncs "miss" rows, check for NULL watermark values first (`SELECT ... WHERE <wm_col> IS NULL`); backfill them or coalesce in the ORDER BY/comparison.
