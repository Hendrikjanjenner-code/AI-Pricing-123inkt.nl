---
name: Feed full-sync cleanup
description: Hoe de periodieke volledige PriceShape-sync in feed-modus verdwenen concurrenten opschoont.
---
Regel: in feed-modus vervangt de ingest alleen de snapshot van vandaag; een periodieke volledige sync (zelfde PRICESHAPE_FULL_SYNC_DAYS-interval als het REST-pad, of ?full=true) draait daarna een aparte opschoning die historische concurrentprijsrijen (en priceshape-offers) verwijdert van concurrenten die vandaag géén rij meer hebben.
**Why:** incrementele feed-syncs laten anders historie van uit de feed verdwenen concurrenten eeuwig staan.
**How to apply:** veiligheidskleppen respecteren — lege snapshot van vandaag = geen opschoning (last-known-good); uitgevinkte concurrenten (importinstellingen) tellen als bewust overgeslagen, niet verdwenen; strikt bron- en shop-gescoped. De laatste volledige feed-run is terugvindbaar via de ImportJob-bestandsnaam voor de volledige feed-sync.
