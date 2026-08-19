---
name: Postgres-only kolommen vs SQLite-tests
description: Hoe Postgres-specifieke kolommen (tsvector, generated columns, GIN-indexen) SQLite-testsuites niet breken
---
Sommige tests maken een verse SQLite-DB via Base.metadata.create_all. Postgres-specifieke kolommen (TSVECTOR, Computed/generated columns) en indexen daarop crashen die DDL.

**Regel:** geef zulke kolommen/indexen `info={"pg_only": True}`; de `@compiles(CreateColumn/CreateIndex, "sqlite")`-hooks in models.py slaan ze dan over.

**Why:** een dutch-tsvector generated column + GIN-index brak alle SQLite-create_all-tests (no such function / can't render TSVECTOR).

**How to apply:** bij elke nieuwe Postgres-only kolom of index in models.py de info-vlag meegeven; code die zo'n kolom leest moet op SQLite een fallback hebben.
