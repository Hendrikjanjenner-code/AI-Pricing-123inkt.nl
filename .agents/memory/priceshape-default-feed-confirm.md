---
name: PriceShape standaard-feed herbevestigen na DB-reset
description: Na een lege/nieuwe dev-DB weigert elke PriceShape-sync tot de standaard-feed opnieuw is bevestigd.
---

Regel: na een database-reset is de ConnectorConfig-rij weg en weigert elke PriceShape-sync met "standaard-feed nog niet bevestigd". Herbevestig via POST /api/connectors/priceshape/save met `{"credentials":{"mode":"feed","feed_url":""}}` (leeg = standaard-feed), daarna POST /sync.

**Why:** expliciete-bron-beleid: de ingebouwde standaard-feed mag nooit stilzwijgend gebruikt worden; de bevestiging leeft alleen in de DB (incident 25-08-2026, herstel na DB-reset).

**How to apply:** volledige herstelvolgorde na lege DB: workflows herstarten (create_all + seeds) → feed bevestigen + sync → Excel-hiërarchie via wizard-API (upload/validate/apply; startup-seed kan de boom al gezet hebben) → modelrun via `services.refresh.run_model_refresh` op een BackgroundSessionLocal-script, NIET via POST /api/model-runs (request-sessie, sneuvelt bij server-reload en laat de run eeuwig op "running" staan). De feed-verbindingstest herkent het brede formaat (vendor_N + itemGroupId) sinds taak #310.
