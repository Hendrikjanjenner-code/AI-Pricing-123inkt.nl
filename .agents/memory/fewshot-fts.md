---
name: Few-shot FTS retrieval
description: Copilot few-shot retrieval uses Postgres dutch FTS with word-overlap fallback; dutch stemmer quirks.
---
Few-shot retrieval (ai_gateway) is primarily Postgres full-text: OR-tsquery over query words with to_tsvector('dutch', question), ranked by ts_rank; any exception rolls back and falls back to Jaccard word-overlap.

**Why:** synonym/reformulated questions must still match; FTS may be unavailable (fail-safe requirement).

**How to apply:** the dutch snowball stemmer is quirky — 'marge'→'marg' but 'marges'→'marges' (no match!). When writing retrieval tests, verify stems via `SELECT to_tsvector('dutch', ...)` first.
