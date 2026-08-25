---
name: Cascaderende productfilters
description: Durable regels voor het 5-niveau productfilter en de exacte SKU-scope.
---

- Scope reist platformbreed via het bestaande hiërarchie-param (diepste node; descendants server-side) — nieuwe module-endpoints erven dit gratis, voeg geen parallel filterkanaal toe.
- Exacte productscope deelt het vrije-zoekterm-param via een prefixconventie. **Why:** aparte params zouden tientallen routes raken. **How to apply:** frontend moet vrije zoektermen altijd van die prefix ontdoen, anders wordt een getypte term ongewild een exact filter (code-reviewbevinding).
- Productfilter-lookups (zoeklijst, scope-resolutie, Copilot-context) moeten shop-geautoriseerd zijn via de standaard allowed-shop-helper; een SKU buiten de toegestane shops gedraagt zich als onbestaand.
- Copilot: een actieve productscope is een server-side toolconstraint (sku-parameters worden vastgezet), nooit alleen prompttekst.
- Deep-links dragen alleen node-ids; hydrateer én valideer de keten server-side en wis de filters bij een ongeldige keten (nooit gemengde data).
