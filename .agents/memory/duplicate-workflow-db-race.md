---
name: Duplicate legacy workflows cause DB race 500s
description: manual .replit workflow entries left alongside auto-generated artifact workflows can double-start a backend service and race on startup DDL, crashing it with intermittent 500s.
---

If a project has both a hand-written `.replit` `[[workflows.workflow]]` entry
(e.g. "API Server", "Pricing Engine") AND the artifact-system's
auto-generated workflow for the same service (named like
"artifacts/<slug>: <service>"), both can be started together (e.g. via a
parent "Project" workflow), launching two instances of the same backend
process concurrently.

Symptom: an intermittent crash on startup like
`psycopg2.errors.UniqueViolation: duplicate key value violates unique
constraint "pg_type_typname_nsp_index"` — this is `Base.metadata.create_all()`
racing with itself across two processes attempting to CREATE TABLE against
the same Postgres DB at the same time. The failed process then can't serve
requests, producing 500s that look like a login/business-logic bug but are
actually an infra race. A duplicate frontend dev-server workflow can also
throw `Port X is already in use`.

**Why:** the artifact system silently generates its own workflow for every
registered artifact's service; nothing prevents a leftover legacy `.replit`
workflow from also targeting the same command/port.

**How to apply:** when debugging intermittent/racy 500s or crash-on-startup
errors in a Replit project, run `listWorkflows()` first and check for
duplicate/overlapping workflows targeting the same artifact or port before
digging into application code. Remove the legacy manual entry with
`removeWorkflow` and keep only the artifact-managed one.
