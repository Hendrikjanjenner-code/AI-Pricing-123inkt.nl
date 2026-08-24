---
name: Hiërarchie auto-assign na feed-sync
description: Concurrency-lessen voor automatische categorietoewijzing van nieuwe feed-producten
---

Automatische toewijzing van nieuwe feed-producten uit de laatst toegepaste Excel-import.

**Rule:** productmatching moet dezelfde per-rij-precedentie volgen als de importvalidatie (over álle producten, niet alleen ongekoppelde), en de "laatste import" mag pas ná het serialisatielock worden bepaald, met een skip zolang een apply nog onderweg is.

**Why:** een product-centrische omkering van de lookup-maps wijst bij identifier-collisions (zelfde code = SKU van A én EAN van B) verkeerde categorieën toe, en zonder lock-vóór-jobkeuze werkt een auto-assign in het apply-claimvenster op een verouderde import door — beide werden op code review afgekeurd als data-integriteitsrisico.

**How to apply:** bij elk nieuw achtergrondproces dat op de hiërarchie of import-staging leunt: lock eerst, kies daarna de bron-import, en skip bij een lopende apply. Testfixtures die een import applyen moeten de daardoor geretireerde auto-boomstaat herstellen, anders breken andere hiërarchiesuites alleen in full-suite runs.
