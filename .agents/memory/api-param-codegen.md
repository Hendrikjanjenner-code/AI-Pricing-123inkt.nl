---
name: API query-param codegen
description: How to add new query params to the FastAPI + generated React client stack
---
New /api query params must be added in three places or the frontend silently can't send them:
1. FastAPI route (artifacts/api-server/routes/...)
2. lib/api-spec/openapi.yaml parameters
3. Regenerate: `cd lib/api-spec && pnpm exec orval --config orval.config.ts`, then root `pnpm run typecheck:libs` to rebuild dist.
**Why:** generated ListXParams types drop unknown params; client-side filtering after a paged fetch gives wrong totals/missing rows (code review rejects this).
**How to apply:** whenever a frontend filter should constrain a paginated server list.
