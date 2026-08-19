---
name: Schedulers uit in tests
description: Achtergrond-schedulers muteren dezelfde tabellen als tests in volledige suite-runs; conftest schakelt ze uit.
---
Een volledige API-suite-run duurt langer dan de opstartvertragingen van de achtergrond-schedulers (feed-sync, DQ-scan, budgetopruiming, key-monitor). Zodra ze middenin de run draaien geven ze StaleDataError en verdwenen testrijen — alleen in de volledige suite, nooit los.

**Why:** TestClient(app) start de lifespan en dus de schedulers in het testproces.

**How to apply:** tests/conftest.py zet alle DISABLE_*-vlaggen via os.environ.setdefault; nieuwe schedulers moeten daar ook een vlag krijgen. Tests die met de klok van productiecode rekenen moeten dezelfde (mogelijk gepatchte) klok gebruiken als de module onder test, niet hun eigen date.today().
