---
name: Signal dedupe per run
description: Engines may publish only one active IntelligenceSignal per dedupe key per run; the enforcing index comes from canonical.py, not create_all.
---
Rule: within a single engine run, publish at most one signal per (engine, signal_type, entity_type, entity_id, shop) — publish_signal's supersede-update can't see pending (unflushed) inserts, so a second publish for the same entity violates uq_signal_active_dedupe at commit.

**Why:** basket engine crashed in full-suite validation when one antecedent SKU appeared in multiple top associations; passed locally because a create_all-fresh DB lacks the partial unique index (it's created by canonical.py, not model metadata).

**How to apply:** dedupe entities before calling publish_signal in any engine loop; when tests pass locally but fail in validation with UniqueViolation on uq_signal_active_dedupe, suspect a fresh DB without canonical.py indexes.
