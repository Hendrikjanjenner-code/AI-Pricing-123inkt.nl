---
name: API curl paths in dev
description: How to reach the FastAPI backend from the shell without double /api prefixes
---
The API server's routes already start with `/api/...`. The shared preview proxy at `localhost:80` mounts it under `/api`, so proxied URLs would double the prefix (`/api/api/...` → 404).

**How to apply:** for shell/curl testing, hit uvicorn directly on its localPort (e.g. `localhost:8080/api/auth/login`). Frontend code uses `${BASE_URL}api/...` which resolves correctly through the proxy.
