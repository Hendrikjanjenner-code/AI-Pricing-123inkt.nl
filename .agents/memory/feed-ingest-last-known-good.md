---
name: Feed ingest last-known-good protection
description: Why PriceShape feed ingestion must never delete a day's fact rows unless it has replacement rows to insert.
---

# Feed ingest must protect last-known-good data

The PriceShape feed ingestion replaces each day's rows with a
delete-then-bulk-insert per fact table (own prices, competitor prices), scoped to
`date == today` (+ `source`).

**Rule:** never run the delete unless there are replacement rows to insert. Guard
every destructive delete on the presence of the corresponding `*_maps` list
(e.g. `if comp_maps:` / `if price_maps:`), and abort the whole ingest early if the
feed yields 0 products AND 0 competitor rows.

**Why:** the feed is polled automatically (scheduler) and by upstream vendors that
can silently return a partial/empty export (auth expiry, schema drift, network
hiccup). A naive delete-then-insert wipes the current day's snapshot when the feed
comes back empty or partial (e.g. products present but zero competitor rows),
breaking the "never break / keep serving last-known-good data" guarantee.

**How to apply:** any new destructive replace step added to `feed_ingest.py` (or a
similar connector ingest) must follow the same "only delete when you have
replacement data" pattern. The fetch already happens before any delete, so a fetch
exception is safe; the danger is the *successful-but-empty* case.
