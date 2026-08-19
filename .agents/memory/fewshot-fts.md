---
name: Few-shot FTS retrieval
description: Copilot few-shot retrieval uses Postgres dutch FTS with word-overlap fallback; dutch stemmer quirks.
---
Few-shot retrieval (ai_gateway) is primarily Postgres full-text: OR-tsquery over query words with to_tsvector('dutch', question), ranked by ts_rank; any exception rolls back and falls back to Jaccard word-overlap.

**Why:** synonym/reformulated questions must still match; FTS may be unavailable (fail-safe requirement).

**How to apply:** the dutch snowball stemmer is quirky — 'marge'→'marg' but 'marges'→'marges' (no match!). When writing retrieval tests, verify stems via `SELECT to_tsvector('dutch', ...)` first.
---
name: Few-shot FTS retrieval
description: Copilot few-shot retrieval via Postgres dutch FTS — thresholds en fail-safe valkuil
---
De FTS-route in get_fewshot_examples vangt élke exception op en valt stil terug op woordoverlap; een NameError (bijv. ontbrekende constante door een slechte merge) schakelt FTS dus onopgemerkt uit.
**Why:** validatie faalde doordat FTS_MIN_RANK nergens gedefinieerd was; de fallback maskeerde dat.
**How to apply:** bij FTS-wijzigingen de retrieval-test draaien; ts_rank van een OR-tsquery met één matchend lexeem in een langere vraag is ~0.0076, dus drempel ≤0.005 houden.
