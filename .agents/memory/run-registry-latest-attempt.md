---
name: Run-registry status semantics
description: Idempotente nachtrun-registraties moeten op de meest recente poging beoordelen, niet op "ooit succes vandaag".
---
Bij per-run registratierijen (append-only) moet "al succesvol gedraaid?" naar de LAATSTE poging kijken; een oude succes-rij mag een latere mislukking (bijv. geforceerde downstream-rerun) niet maskeren.
**Why:** anders wordt een noodzakelijke herstart permanent overgeslagen en blijft downstream-data stale.
**How to apply:** query op laatste rij per (run_date, shop, engine) of houd één atomair bijgewerkte unieke rij; run-historie-FK's naar dim_shop krijgen ON DELETE CASCADE zodat shop-verwijdering nooit blokkeert.
