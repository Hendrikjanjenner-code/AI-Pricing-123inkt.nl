---
name: configureWorkflow does not expand $PORT
description: Why artifact.toml dev run commands with literal $PORT fail when passed to configureWorkflow, and how to fix it.
---

`artifact.toml` `[services.development].run` commands often reference `$PORT`
(e.g. `uvicorn main:app --port $PORT`), relying on the artifact's own launch
mechanism to inject `PORT` as an env var before shell-expanding it.

When manually registering a workflow via `configureWorkflow` with that same
command string, `$PORT` is **not** expanded — it comes through empty, so
`--port $PORT --reload` becomes `--port --reload` and uvicorn/click errors
with something like `Invalid value for '--port': '--reload' is not a valid
integer`.

**Why:** `configureWorkflow` runs the literal command; it doesn't source the
artifact's env injection layer that live artifact-managed workflows get.

**How to apply:** when hand-registering a workflow for an artifact whose
`artifact.toml` uses `$PORT`, replace it with the artifact's actual
`localPort` value and export `PORT=<port>` (and `BASE_PATH` for frontends)
explicitly in the command, e.g.
`PORT=8080 uvicorn main:app --host 0.0.0.0 --port 8080 --reload`.
