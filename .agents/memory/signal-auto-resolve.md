---
name: Signal auto-resolve scoping
description: Lifecycle rules for auto-resolving intelligence signals per engine run.
---
Rule: auto-resolving a signal requires the full signal identity (shop + signal_type + entity_type + entity_id) AND a trustworthy current source snapshot of that same shop.

**Why:** unscoped resolution lets one shop's data resolve another shop's signals, stale rows keep resolved conditions "active", a newer run of another shop yields an empty own-source set, and an empty/failed source ingest would mass-resolve real alerts. Code review rejects all four.

**How to apply:** compute the latest source date per shop (filter shop_id, or exclude SKUs provably belonging to other shops); build the still-active key set from the full qualifying set BEFORE top-N truncation; skip resolution entirely when the shop has no current source rows (no data ≠ resolved); only touch status "active" so it stays idempotent.
