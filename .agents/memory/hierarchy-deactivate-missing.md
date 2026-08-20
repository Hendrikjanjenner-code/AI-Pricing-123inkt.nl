---
name: Hierarchy deactivate_missing is global
description: Import-apply met deactivate_missing deactiveert ALLE import-nodes buiten het bestand; shared-DB tests moeten snapshot/restore doen.
---

**Regel:** `apply_job(..., deactivate_missing=True)` behandelt het importbestand als volledige vervanging en deactiveert elke actieve node met `source="import"` die niet in het bestand staat — DB-breed, niet alleen test-nodes. Autobuild skipt bovendien zodra er één actieve niet-auto node bestaat, dus autobuild-tests moeten de vreemde boom tijdelijk deactiveren en herstellen.

**Why:** een full-suite run op de gedeelde dev-DB heeft hiermee ooit de complete echte categorieboom uitgeschakeld (UI: "Geen hiërarchie beschikbaar") en liet autobuild-tests flaky falen.

**How to apply:** elke test die deactivate_missing of autobuild raakt: vooraf ids van actieve niet-test (import/handmatige) nodes vastleggen, in een `finally` heractiveren. Bijkomend: productcodes in hiërarchie-exports zijn feed-product-id's (`raw_attributes.id`), match_method `feed_id`.
