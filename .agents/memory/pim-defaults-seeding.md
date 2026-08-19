---
name: PIM defaults seed-once
description: ensure_defaults must never reseed after an admin intentionally empties a PIM reference table
---
PIM reference-data seeding (attributes/channels/families) is one-time, guarded by an audit_log marker (entity_type=pim_defaults, action=defaults_seeded) plus a process-local flag.

**Why:** the old count==0 guard reseeded defaults on every list read, so deleting the last attribute/channel/family "succeeded" but the defaults reappeared on the next refresh — code review rejects that.

**How to apply:** any "seed if empty" helper called from ordinary read endpoints needs a persistent seeded-once marker, not just an emptiness check.
