---
name: Concurrentprofiel Excel-schema
description: Duurzame modelleringsregels voor het importklare concurrentprofielwerkboek.
---

Gebruik voor bedrijfsprofielen een lang formaat met één rij per kenmerk. Zo heeft iedere waarde eigen status, informatielaag, confidence, peildatum en bron zonder herhaalde metakolommen per kenmerk.

Houd juridische concernrelaties en commerciële lidmaatschappen in hetzelfde relatieblad technisch strikt gescheiden via een relatieklasse. Een commercieel verband is nooit bewijs voor eigendom of zeggenschap.

**Why:** Deze vorm blijft compact voor gebruikers, maar is zonder herontwerp valideerbaar en importeerbaar. Expliciete metadata per waarde voorkomt dat onbekend als nul/leeg wordt geïnterpreteerd of Creditsafe-context stil wordt overschreven.

**How to apply:** Nieuwe import- of exportfuncties moeten de vaste v1-sleutels en keuzevelden respecteren. Nieuwe profielvelden of technische keuzes vereisen een nieuwe schemaversie.