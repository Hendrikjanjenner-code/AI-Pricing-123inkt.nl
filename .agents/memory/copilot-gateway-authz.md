---
name: Copilot gateway authz & scope
description: Waarom scope- en permissie-afdwinging in de AI-gateway zit, niet in de semantic layer of het model.
---
Regel: het LLM mag nooit scope- of autorisatie-ids aanleveren; het geeft alleen namen (bv. een categorienaam), de gateway resolvet en injecteert ids server-side en dropt model-geleverde scope-args. Afdelingspermissies worden in de gateway dubbel afgedwongen: gefilterd toolaanbod én weigering bij uitvoering.
**Why:** prompt-injectie kan anders cross-shop/cross-afdeling data opvragen; alleen toolaanbod filteren is onvoldoende omdat modellen ongeadverteerde functies kunnen aanroepen.
**How to apply:** bij elke nieuwe semantic function of scope-parameter: koppel een permissie, publiceer nooit ruwe ids in het tool-schema, en geef node-niveau filters dezelfde descendant-semantiek als SKU-filters.
