---
name: Duplicate API Server workflow race
description: Recurring cause of backend-down / login-500 — a legacy non-prefixed "API Server" workflow duplicating the artifact-managed one.
---

# Duplicate "API Server" workflow crashes the backend

**Symptom:** Backend is down; frontend shows login 500 / "GET /me failed". API Server logs show:
`sqlalchemy.exc.IntegrityError: duplicate key value violates unique constraint "pg_type_typname_nsp_index"` on a `CREATE TABLE` (e.g. connector_config), and the artifact workflow `artifacts/api-server: API Server` fails with `[Errno 98] Address already in use`. Vite artifacts may also show "Port already in use".

**Root cause:** A second, legacy workflow named just **`API Server`** (no `artifacts/` prefix) exists alongside the artifact-managed `artifacts/api-server: API Server`. Both run uvicorn on port 8080 and race on `Base.metadata.create_all()`, so one process crashes the whole backend at startup.

**Why it keeps coming back:** Tasks that need to test the backend sometimes create a bare `API Server` workflow via `configureWorkflow` (because the literal `$PORT` from artifact.toml doesn't shell-expand through configureWorkflow, so they hardcode a port). If left behind, it duplicates the canonical artifact workflow. First fixed once, reintroduced later, seen again.

**Fix:**
1. `removeWorkflow({ name: "API Server" })` (the non-prefixed legacy one — NEVER remove the `artifacts/...` ones; those are canonical/artifact-managed).
2. `fuser -k 8080/tcp` to clear any orphan uvicorn still holding the port.
3. `restart_workflow("artifacts/api-server: API Server")`.
4. Orphaned vite processes can also hold deck ports → just restart each `artifacts/<deck>: web` workflow.

**How to apply:** Whenever the backend is mysteriously down or login returns 500, run `listWorkflows()` first and look for a bare `API Server` (or any non-`artifacts/`-prefixed duplicate). The canonical workflows are all prefixed `artifacts/`.
