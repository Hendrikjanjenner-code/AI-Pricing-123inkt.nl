---
name: Feed-ingest geheugengrens & bronredactie
description: Waarom elk PriceShape-parse-pad schijfgebonden moet zijn en hoe bron-URL's veilig getoond worden.
---

- **Waarom:** de feed is honderden MB's; élk formaat (ook het brede CSV-standaardformaat, niet alleen streaming JSON) moet naar schijf en in begrensde batches verwerkt worden. Nieuwe parse-paden nooit via volledige response-bytes of lijst-normalisatie routeren, anders OOM't de VM.
- Guard-volgorde: tellingen in read-only passes vóór welke delete dan ook; empty-feed-guard beslist vóór de eerste write. Filters moeten idempotent zijn omdat her-iteratie verse rijen oplevert.
- Weigering onbevestigde standaard-feed: de foutmelding mag NOOIT de substring "niet geconfigureerd" bevatten (wordt gemapt naar stille not_configured-status). Bevestiging = config opslaan of de feed-URL-env-var zetten.
- URL-redactie voor UI/status: nooit op tokenlengte-regex vertrouwen — parseer de URL en toon alleen schema+host; userinfo, pad, query en fragment altijd maskeren (code review wijst lengte-gebaseerde redactie af als credential-lek).
