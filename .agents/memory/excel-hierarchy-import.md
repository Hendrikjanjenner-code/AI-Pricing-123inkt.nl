---
name: Excel-hiërarchie re-import
description: Hoe en wanneer de klant-Excel producthiërarchie opnieuw geïmporteerd moet worden
---
De canonieke categorieboom komt uit de klant-Excel in attached_assets (0_202608141341_0_Product_hierarchieen_met_ids_*.xlsx: optionId/productcode/path, |-gescheiden, 114k rijen, 1.474 unieke paden van 2-6 niveaus — paden zijn echte categorieën, géén productnamen).

**Regel:** na een dev-DB-reset (import_jobs vrijwel leeg) is de toegepaste boom weg; re-import via de wizard: POST /api/product-hierarchy/import/upload (multipart file) → /import/{id}/validate → /import/{id}/apply. Mapping wordt automatisch gedetecteerd. Verwacht: 1.822 import-nodes actief, auto_categorie-boom inactief, ~10,5k assignments.

**Waarschuwing:** voer apply nooit uit terwijl de apitests-suite draait — deactivate_missing/autobuild-tests muteren dezelfde tabellen en de suite-restore zet jouw zojuist toegepaste state terug/omver. Wacht tot pytest klaar is en controleer daarna `select source,is_active,count(*) from product_hierarchy_nodes group by 1,2`.
