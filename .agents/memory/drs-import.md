---
name: DRS daily import
description: Constraints that keep the DRS XLSX daily import from timing out or crashing
---

# DRS daily import (routes/drs.py)

The DRS DATAREPORT XLSX is uploaded daily and can hold thousands of SKU rows.

## Rule: no per-row DB round-trips
Pre-load existing `DimProduct` and `DimCategoryHierarchy` into dicts (one query each)
and look up in-memory. Do NOT `db.query(...).filter(sku_id==pc).first()` per row —
that turns one import into thousands of SELECTs and trips the Replit proxy timeout
("Hmm... We couldn't reach this app" HTML page).

**Why:** the proxy returns a generic HTML timeout page on slow requests; the frontend
then showed it as a JSON parse error.

## Rule: no per-row audit inserts
Write a single summary audit_log entry for the whole import, not one per SKU — per-row
inserts double the write volume and contribute to the timeout.

## Rule: truncate every string field to its VARCHAR limit before persist
Real product names/paths exceed column limits → `StringDataRightTruncation`. Use the
`_trunc(value, limit)` helper for every text column (product_name 500, sku_id 100,
oem_code 100, brand/category/product_group 255, product_type 50, category_name 255,
path 1000).

## Rule: rollback before writing failed-job state
In the except block, `db.rollback()` FIRST. After a flush error the session is poisoned;
calling `db.commit()` on it raises PendingRollbackError, which escapes as an HTML 500
instead of a clean JSON error. Wrap the job-status commit in its own try/except.
