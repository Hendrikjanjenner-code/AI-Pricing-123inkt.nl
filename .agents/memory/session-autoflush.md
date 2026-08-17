---
name: SessionLocal autoflush=False pitfall
description: API sessions don't autoflush; multi-step pipelines must flush explicitly between write and read phases.
---
The API's SQLAlchemy `SessionLocal` is created with `autoflush=False`. Code that adds rows and then queries them in the same session sees stale/empty results unless it calls `db.flush()` between steps.

**Why:** Silent failure mode — queries simply return nothing pending; no error is raised.

**How to apply:** In multi-phase engine runs or import loops that read rows written earlier in the same transaction, add `db.flush()` after each write phase.
