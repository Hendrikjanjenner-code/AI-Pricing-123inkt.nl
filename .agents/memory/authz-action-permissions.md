---
name: Granular authz action permissions
description: How the department/permission model enforces reads and writes; pitfalls for role seeds and legacy tests.
---
The authz model enforces two layers per request: view permission per /api segment (any method) and an action permission for writes (POST/PUT/PATCH/DELETE) via required_action_permission — approve/reject/override paths map to *.approve, other writes to a per-segment code. Where an action rule exists, require_role defers to the permission entirely (grant works, revoke works); without a rule, legacy role checks decide.

**Why:** the Roles & Rights matrix must actually control sensitive actions (code review rejected a view-only middleware); but blanket permission overrides on all segments would widen access (e.g. copilot budget config).

**How to apply:**
- New mutation endpoints in a covered segment are automatically permission-gated; new sensitive segments need an entry in WRITE_PERMISSIONS/APPROVE_PERMISSIONS.
- Legacy capability nuance: analysts could run competition simulations (competition.edit) but NOT data imports — keep data.edit out of the analyst role base and out of data_bi department defaults, or the RBAC matrix test (analyst 403 on uploads write) fails.
- Tests creating fresh viewer/analyst users that expect broad read access must call tests/authz_helpers.grant_legacy_views(username).
