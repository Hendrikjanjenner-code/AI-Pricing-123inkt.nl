---
name: Local API runtime quirks
description: Non-obvious things needed to run/test the FastAPI api-server locally in this environment.
---

# Running api-server locally for testing

- **Startup hangs at "Waiting for application startup" unless the scrape scheduler is disabled.**
  Set `DISABLE_SCRAPE_SCHEDULER=true` when launching uvicorn manually, otherwise the lifespan
  never reaches "Application startup complete" in this container.
  **Why:** the background scrape scheduler started in `main.py`'s lifespan blocks startup here.
  **How to apply:** `DISABLE_SCRAPE_SCHEDULER=true PORT=8080 uvicorn main:app --host 0.0.0.0 --port 8080`.

- **Background servers die between separate bash tool calls.** Start the server AND run all curl
  tests inside a single shell command (`uvicorn ... & SRV=$!; sleep 12; curl ...; kill $SRV`).

- **Login endpoint is `POST /api/auth/login`** (prefix `/api/auth`), and the JSON response field is
  `token` (plus a `user` object) — NOT `access_token`.

- **`seed_database()` re-inserts the 4 demo users** (guarded only on `DimProduct.count()`), so if
  `seed_users_only()` already ran, calling `seed_database()` raises a unique-violation on
  `users.email`. To seed demo data on a DB that already has users, clear `users` first or run on a
  fresh DB. Use `SEED_DEMO_DATA=true`.
