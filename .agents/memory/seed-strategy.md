---
name: Seed strategy
description: How startup seeding is structured — always-users vs env-gated demo data.
---

## Rule
`seed_users_only()` is always called on startup (creates 4 demo accounts if none exist).  
`seed_database()` is only called when `SEED_DEMO_DATA=true` (or `1`/`yes`).

**Why:** Pilot deployments should start with an empty DB and import real data via CSV. Demo data should not auto-populate production environments. But login must always work on a fresh DB.

**How to apply:** Any new seeder that seeds _demo_ product/price/sales data should be called only inside the `SEED_DEMO_DATA` block in `main.py`. User-account seeders go in `seed_users_only()`.
