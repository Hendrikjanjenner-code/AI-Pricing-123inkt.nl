---
name: Testsuite draait in eigen testdatabase
description: Sinds taak #312 draait pytest in "<appdb>_test"; app-data is veilig, maar suite-runs delen die testdatabase nog wel.
---

Regel: `tests/conftest.py` zet DATABASE_URL vóór elke import om naar een eigen testdatabase (`<appdb>_test`, overschrijfbaar via TEST_DATABASE_URL), met harde guard op de effectieve libpq-dbnaam (ook `?dbname=`-bypass en `service=` geweigerd) en een sessie-fixture die één TestClient-startup doet voor schema/seeds.

**Why:** de suite draaide eerder op de app-database en wiste bij elke completion-validatie de feed-bevestiging en alle concurrentprijzen (terugkerende gebruikersklacht, opgelost in taak #312).

**How to apply:** app-data is nu veilig tijdens validatieruns; wél delen gelijktijdige suite-runs (eigen run + completion-validatie) nog dezelfde testdatabase — vermijd parallel draaien of reken op de bestaande advisory-locks. De testdatabase houdt residu tussen runs, dus alle bestaande shared-DB-isolatieconventies blijven gelden. Handmatige psql-checks van app-data blijven gewoon via $DATABASE_URL (die wijst buiten pytest nog naar de app-DB).
