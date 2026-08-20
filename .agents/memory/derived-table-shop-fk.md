---
name: Afgeleide tabellen met shop-FK
description: Waarom nieuwe engine-output tabellen met shop_id-FK ON DELETE CASCADE nodig hebben in deze codebase.
---

**Regel:** elke nieuwe afgeleide/engine-output tabel met een `shop_id`-FK naar `dim_shop` krijgt `ForeignKey("dim_shop.id", ondelete="CASCADE")`.

**Why:** de testsuite bevat tientallen modules die een eigen test-DimShop aanmaken en in hun teardown verwijderen. Die teardowns kennen nieuwe tabellen niet; zodra een engine-run (die vaak indirect meedraait, bv. via `run_competitor_rankings`) rijen voor hun shop schrijft, faalt de shop-delete op de FK — alleen in full-suite runs, ver van de veroorzakende taak.

**How to apply:**
- Zet CASCADE in het model bij aanmaak van de tabel.
- In de dev-DB bestaat de tabel dan mogelijk al zonder CASCADE (`create_all` wijzigt niets): eenmalig `ALTER TABLE ... DROP CONSTRAINT ...; ADD CONSTRAINT ... ON DELETE CASCADE` draaien.
- Geldt niet voor brondata-tabellen waar stille verwijdering gevaarlijk is; het gaat om herberekenbare afgeleide data.
