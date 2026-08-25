---
name: Hiërarchie test-importjobs vervuilen auto-assign
description: Test-applies met status "geimporteerd" worden de "laatst toegepaste import" en breken auto_assign_new_products voor echte feed-producten.
---

Regel: elke test die een hiërarchie-import uploadt/applyt moet (1) een unieke, herkenbare bestandsnaam per testrun gebruiken en (2) in de teardown óók de ImportJob-rijen verwijderen (eerst assignments.import_job_id nullen, changelog- en stagingrijen wissen).

**Why:** `auto_assign_new_products` (post-feed-sync hook) matcht tegen de staging-rijen van de laatst toegepaste `product_hierarchy`-ImportJob. Honderden achtergebleven mini-testjobs ("hier.csv", status geimporteerd) maskeerden de echte Excel-import (job 1, 114k staging-rijen), waardoor het hele assortiment ongekoppeld bleef en categoriefilters lege ranking-data gaven (incident 25-08-2026).

**How to apply:** gebruik de gedeelde helpers in tests/conftest.py: `register_hierarchy_test_prefix` + `purge_hierarchy_import_jobs(db, PFX)` in de fixture-teardown, of de job-id-variant (`register_hierarchy_test_job_ids` / `purge_hierarchy_import_jobs_by_ids`) als de job de echte Excel-bestandsnaam draagt (seed-tests: run_seed-fixture). Registreer vóór enige assert; een autouse sessie-fixture faalt de suite bij achtergebleven "geimporteerd"-residu. Herstel na vervuiling: residu-jobs verwijderen en `auto_assign_new_products` eenmaal draaien (eigen sessie, advisory-lock-serialisatie zit erin). Actieve assignments horen bij de import-boom via bron `auto_import`; superseded `auto_categorie`-rijen bij de gepensioneerde auto-boom zijn normaal en hoeven niet gereactiveerd.
