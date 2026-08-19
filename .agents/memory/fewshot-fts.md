---
name: Few-shot FTS retrieval
description: Copilot few-shot retrieval uses Postgres dutch FTS with word-overlap fallback; stemmer/rank quirks and silent-fallback trap.
---
Few-shot retrieval (ai_gateway) is primarily Postgres full-text: OR-tsquery over query words against the STORED generated column question_tsv (GIN-indexed), ranked by ts_rank; any exception rolls back and falls back to Jaccard word-overlap.

**Why:** synonym/reformulated questions must still match, and FTS may be unavailable (fail-safe requirement). But because the caller catches every exception, a NameError or missing column silently disables FTS — a validation failure was once masked this way.

**How to apply:**
- The auto-migrator skips Computed columns; generated columns need manual DDL in migrate.py's _MANUAL_INDEXES.
- ts_rank normalizes on length: one matching stem on a short question scores ~0.008, so keep the min-rank cutoff very low (≈0.003, ≤0.005); the @@ filter already excludes zero-overlap questions.
- The dutch snowball stemmer is quirky — 'marge'→'marg' but 'marges'→'marges' (no match). Verify stems via `SELECT to_tsvector('dutch', ...)` when writing retrieval tests.
- After FTS changes, run the retrieval test explicitly; the fallback will hide breakage otherwise.
- question_tsv is Postgres-only: column and GIN index carry info={"pg_only": True}; compiles-hooks in models.py skip them in SQLite DDL.
- Keep exactly ONE authoritative FTS_MIN_RANK definition, right next to its use; a duplicate or dropped definition after a merge silently disables FTS via the fallback.
- FTS tests failing with [] usually mean the primary path is throwing, not that ranking changed; one shared stem in a longer question ranks ~0.0076, irrelevant questions 0.0.
