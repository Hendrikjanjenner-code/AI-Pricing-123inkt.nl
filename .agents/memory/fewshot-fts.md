---
name: Few-shot FTS retrieval
description: Copilot few-shot retrieval uses Postgres dutch FTS with word-overlap fallback; dutch stemmer quirks and fail-safe trap.
---
Few-shot retrieval (ai_gateway) is primarily Postgres full-text: OR-tsquery over query words with to_tsvector('dutch', question), ranked by ts_rank; any exception rolls back and falls back to Jaccard word-overlap.

**Why:** synonym/reformulated questions must still match; FTS may be unavailable (fail-safe requirement). But because the FTS route swallows every exception, a coding error (e.g. an undefined constant after a bad merge) silently disables FTS — the fallback masks it.

The tsvector is a STORED generated column (question_tsv) with a GIN index; the auto-migrator skips Computed columns, so generated columns need manual DDL in migrate.py's _MANUAL_INDEXES. ts_rank normalizes on document length: a strong single-stem match on a short question scores only ~0.008, so the min-rank cutoff must stay very low (≤0.003–0.005) — the @@ filter already excludes zero-overlap questions.

**How to apply:** the dutch snowball stemmer is quirky — 'marge'→'marg' but 'marges'→'marges' (no match!). When writing retrieval tests, verify stems via `SELECT to_tsvector('dutch', ...)` first, and run the retrieval tests after any FTS change to catch silently-disabled FTS.

**FTS_MIN_RANK trap:** de FTS-route vangt élke exception op en valt stil terug op woordoverlap; een NameError (bijv. ontbrekende of dubbel gedefinieerde constante door een slechte merge) schakelt FTS dus onopgemerkt uit en levert lege resultaten. Houd één gezaghebbende FTS_MIN_RANK-definitie vlak bij het gebruik en draai de retrieval-tests na FTS-wijzigingen.
