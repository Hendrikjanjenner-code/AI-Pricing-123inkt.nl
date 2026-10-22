---
name: Testsuite draait in eigen testdatabase
description: Pytest gebruikt een afzonderlijke testdatabase; let op gedeelde runs en reeds omgezette databaseconfiguratie.
---

Regel: `tests/conftest.py` zet DATABASE_URL vóór elke import om naar een eigen testdatabase (`<appdb>_test`, overschrijfbaar via TEST_DATABASE_URL), met harde guard op de effectieve libpq-dbnaam (ook `?dbname=`-bypass en `service=` geweigerd) en een sessie-fixture die één TestClient-startup doet voor schema/seeds.

**Why:** de suite draaide eerder op de app-database en wiste bij elke completion-validatie de feed-bevestiging en alle concurrentprijzen (terugkerende gebruikersklacht).

**How to apply:** app-data is nu veilig tijdens validatieruns; wél delen gelijktijdige suite-runs (eigen run + completion-validatie) nog dezelfde testdatabase — vermijd parallel draaien of reken op de bestaande advisory-locks. De testdatabase houdt residu tussen runs, dus alle bestaande shared-DB-isolatieconventies blijven gelden. Handmatige psql-checks van app-data blijven gewoon via $DATABASE_URL (die wijst buiten pytest nog naar de app-DB).

Testhelpers moeten rekening houden met een al omgezette databaseconfiguratie, in plaats van zelf altijd opnieuw een testdatabasenaam af te leiden.

**Why:** Een geïsoleerde PostgreSQL-test slaagde zonder conftest, maar faalde in de volledige suite omdat hij een extra `_test` toevoegde aan de reeds geselecteerde testdatabase.

**How to apply:** Gebruik binnen de suite de reeds bewaakte testverbinding; houd bij standalone runs een afzonderlijke veiligheidscontrole ten opzichte van de echte app-database. Een willekeurig schema alleen is geen reden om de app-database te gebruiken.
