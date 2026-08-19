---
name: Few-shot FTS retrieval
description: Copilot few-shot retrieval via Postgres dutch FTS with word-overlap fallback; thresholds, stemmer quirks, fail-safe trap.
---
Few-shot retrieval (ai_gateway) is primarily Postgres full-text: OR-tsquery over query words with to_tsvector('dutch', question), ranked by ts_rank; any exception rolls back and falls back to Jaccard word-overlap.

**Why:** synonym/reformulated questions must still match; FTS may be unavailable (fail-safe requirement). But because the FTS route swallows every exception, a coding error (e.g. an undefined or duplicated constant after a bad merge) silently disables FTS — the fallback masks it and yields empty/degraded results. Keep one authoritative FTS_MIN_RANK definition close to its use.

The tsvector is a STORED generated column (question_tsv) with a GIN index; the auto-migrator skips Computed columns, so generated columns need manual DDL in migrate.py's _MANUAL_INDEXES. ts_rank normalizes on document length: a strong single-stem match on a short question scores only ~0.008, so the min-rank cutoff must stay very low (FTS_MIN_RANK ≈ 0.003) — the @@ filter already excludes zero-overlap questions; one shared stem in a longer question ranks ≈ 0.0076, irrelevant questions 0.0.

**How to apply:** the dutch snowball stemmer is quirky — 'marge'→'marg' but 'marges'→'marges' (no match!). When writing retrieval tests, verify stems via `SELECT to_tsvector('dutch', ...)` first, and run the retrieval tests after any FTS change to catch silently-disabled FTS. FTS tests failing with [] usually mean the primary path is throwing, not that ranking changed.
