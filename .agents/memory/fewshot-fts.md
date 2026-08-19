---
name: Few-shot FTS retrieval
description: Copilot few-shot retrieval uses Postgres dutch FTS with a silent word-overlap fallback; the fallback masks real FTS bugs.
---
Few-shot retrieval is primarily Postgres dutch full-text search; ANY exception falls back silently to word-overlap. A NameError (e.g. a constant lost in a bad merge) therefore disables FTS unnoticed — after FTS changes, run the reformulation retrieval test explicitly.

**Why:** reformulated/synonym questions must still match and FTS may be unavailable (fail-safe requirement), but the fallback masks real FTS bugs.

**How to apply:** after any FTS or merge change, verify FTS is actually used (not the fallback); the dutch snowball stemmer is quirky (plural forms may not stem to the same root), so verify stems via `SELECT to_tsvector('dutch', ...)` when writing retrieval tests.
