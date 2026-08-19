---
name: Rankings na feed-sync
description: Ontwerpregels voor de automatische rankings-refresh na elke feed-sync
---
- Elke feed-sync-afronding (in-app scheduler, scheduled_sync.py én handmatige connector-sync) triggert een fout-tolerante CIS+rankings-refresh; falen mag de sync nooit meeslepen maar moet als EngineRun (engine_name="rankings") zichtbaar zijn.
- **Why:** dashboardrankings moeten altijd bij de laatste feed horen; een stil falende refresh maskeert verouderde data.
- Rankings zijn dag-gekeyd (run_date): bij een herrun op dezelfde dag moet previous_rank uit de zojuist te vervangen dagsnapshot komen, niet uit gisteren — anders verdwijnen intra-day verschuivingen.
- De refresh serialiseert met de feed-ingest via dezelfde PostgreSQL advisory key (routes/connectors._advisory_key("priceshape")), blokkerend met lock_timeout; anders lezen rankings een half-vervangen snapshot.
- GET /rankings levert computed_at/last_feed_sync_at/stale/changed; "changed" alleen als er een vorige run bestond (allereerste run mag geen banner geven).
- POST /rankings/run is een achtergrondjob (engine_jobs, shop_id als query-param) — synchrone aanroepen liepen tegen de 15s-frontend-timeout en proxy-timeouts aan.
