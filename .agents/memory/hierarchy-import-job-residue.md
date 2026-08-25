---
name: Hiërarchie test-importjobs vervuilen auto-assign
description: Test-applies met status "geimporteerd" worden de "laatst toegepaste import" en breken auto_assign_new_products voor echte feed-producten.
---

Regel: elke test die een hiërarchie-import uploadt/applyt moet (1) een unieke, herkenbare bestandsnaam per testrun gebruiken en (2) in de teardown óók de ImportJob-rijen verwijderen (eerst assignments.import_job_id nullen, changelog- en stagingrijen wissen).

**Why:** `auto_assign_new_products` (post-feed-sync hook) matcht tegen de staging-rijen van de laatst toegepaste `product_hierarchy`-ImportJob. Honderden achtergebleven mini-testjobs ("hier.csv", status geimporteerd) maskeerden de echte Excel-import (job 1, 114k staging-rijen), waardoor het hele assortiment ongekoppeld bleef en categoriefilters lege ranking-data gaven (incident 25-08-2026).

**How to apply:** volg het patroon in tests/test_product_hierarchy.py (PFX-bestandsnaam + job-cleanup in fixture-teardown; bewakende test `test_testimport_kan_geen_laatst_toegepaste_import_blijven`). Herstel na vervuiling: residu-jobs verwijderen en `auto_assign_new_products` eenmaal draaien (eigen sessie, advisory-lock-serialisatie zit erin). Actieve assignments horen bij de import-boom via bron `auto_import`; superseded `auto_categorie`-rijen bij de gepensioneerde auto-boom zijn normaal en hoeven niet gereactiveerd.
