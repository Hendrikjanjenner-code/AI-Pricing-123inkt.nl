---
name: Data source status cards need persisted history
description: Any "last sync / last import" UI card must be backed by a persisted job record, not just a live response.
---

Endpoints that trigger an action against an external system (e.g. an admin-triggered sync) must write a durable record (an ImportJob-style row) of the attempt — status, timestamp, row counts — every time they run, in addition to returning the live JSON response to the caller.

**Why:** A "last sync" status card in the UI reads from history, not from the transient response of the trigger call. If the endpoint only returns JSON without persisting, the card has nothing to query and silently shows "never synced" even right after a successful sync. This was flagged in code review as a functional gap, not a cosmetic one.

**How to apply:** When building or reviewing any dashboard card that shows "last X" for an action a user or scheduler can trigger (sync, refresh, scrape, export), verify the triggering endpoint writes a row to whatever history table backs that card. Wrap the persistence in try/except so a persistence failure never blocks the primary response to the caller.
