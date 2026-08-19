---
name: Keyset pagination & NULL watermarks
description: Row-tuple keyset pagination silently drops NULL-watermark rows; coalesce both sides.
---
A keyset condition like `(wm, pk) > (:lk_wm, :lk_pk)` evaluates to NULL (excluded) for rows whose watermark is NULL — those rows are never paged past the first page and silently disappear from syncs.
**Why:** legacy rows from before a watermark column was introduced have NULL there; a BigQuery export missed them until a pagination test on a shared DB caught it.
**How to apply:** COALESCE the watermark to a fixed minimum timestamp on BOTH sides of the comparison and in ORDER BY; keep the caller's last_key construction consistent (map None to the same minimum).
