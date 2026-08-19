---
name: Few-shot FTS retrieval
description: Copilot few-shot retrieval uses Postgres dutch FTS with word-overlap fallback; stemmer quirks, rank thresholds, and the silent-fallback trap.
---
Few-shot retrieval (ai_gateway) is primarily Postgres full-text: OR-tsquery over query words against the dutch tsvector, ranked by ts_rank; ANY exception falls back silently to Jaccard word-overlap. A NameError (e.g. a constant lost in a bad merge) therefore disables FTS unnoticed — after FTS changes, run the reformulation retrieval test explicitly.

**Why:** reformulated/synonym questions must still match, and FTS may be unavailable (fail-safe requirement), but the fallback masks real FTS bugs.

**How to apply:**
- ts_rank normalizes on length: one matching stem in a longer OR-query ranks ~0.0076, a strong short match ~0.008. Keep the min-rank cutoff very low (≤0.005; currently 0.003) — the `@@` filter already excludes zero-overlap questions.
- The tsvector is a STORED generated column (question_tsv) with a GIN index; the auto-migrator skips Computed columns, so it needs manual DDL in migrate.py. SQLite (isolated tests) can't compile TSVECTOR/to_tsvector — models.py renders the column as plain TEXT there via a CreateColumn compile hook.
- The dutch snowball stemmer is quirky — 'marge'→'marg' but 'marges'→'marges' (no match!). Verify stems via `SELECT to_tsvector('dutch', ...)` when writing retrieval tests.
