---
name: Replit deploy health-checks the service BASE path
description: Why a FastAPI/service must return 2xx on its bare base path (e.g. /api), not only /healthz, or the deployment shows "This app isn't live yet".
---

# Replit deployment health-checks the service base path, not your healthz path

On Replit monorepo deployments, the platform router health-checks each runnable
service at its **registered base path** (the `paths = [...]` value in
`artifact.toml`, e.g. `/api`) — NOT the `[services.production.health.startup]`
`path` you configured (e.g. `/api/healthz`). Deployment logs show this as
`healthcheck failed error=healthcheck /api returned status 500`.

If the app has **no route at the bare base path**, that path returns 404 once the
app is up (and 500/502 while still cold-booting). A health check that only ever
gets non-2xx on the base path can prevent the deployment from being promoted /
kept "live", so the public URL serves Replit's **"This app isn't live yet"**
placeholder on ALL paths — even while `getDeploymentInfo` reports
`isDeployed=true`. `isDeployed=true` ≠ "currently serving traffic".

**Fix:** add a trivial `GET ""`/`GET "/"` route on the service base path that
returns a plain `200` (e.g. `{"status":"ok"}`). Keep the richer diagnostics on
`/healthz` / `/health`.

**Why:** the startup probe passing (`/api/healthz` → 200) is not enough; the
base-path probe must also succeed for the VM to stay promoted.

**How to apply:** any FastAPI/Express/etc. service mounted under a base path on a
Replit deployment must answer 2xx on that bare base path. When you see
"This app isn't live yet" + `isDeployed=true` + `healthcheck <base> returned 500`
in logs, this is the first thing to check.

**Secondary risk:** heavy cold start (pandas/numpy/sklearn imports + create_all +
migrations) blocks ~30-40s before uvicorn binds, during which the base path
returns 500/502. Usually tolerated once, but if promotion stays flaky, defer
non-critical startup work (seeds, owner-admin ensure) to a background task so the
server binds and answers health checks fast.
