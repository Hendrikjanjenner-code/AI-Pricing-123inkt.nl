---
name: Channelmanager without final external file contracts
description: User-approved scope for building before DRS, MacroRecorder, PriceShape examples and shop rules arrive.
---

Build the complete internal Channelmanager workflow now, without waiting for real PriceShape advice, MacroRecorder export, DRS readback files, or confirmed shop rules. Make the mappings and rules configurable so they can be adapted later.

**Why:** The user explicitly asked “kun je wel alles bouwen nu zonder 1,2,3,4 dat we het later aanpassen?” after being told those four inputs were missing.

**How to apply:** Missing examples no longer block the generic internal workflow. Do not claim verified compatibility with external formats or invent confirmed business rules. Clearly identify provisional settings and require explicit human approval. This authorization does not authorize live price pushes or production publication.

PriceShape currently receives an input CSV from DRS. The user states that PriceShape also has an API; its specific supported input and advice-return endpoints are not yet confirmed.

**Why:** The user described the existing operational feed when asking how to connect Pricing Hub.

**How to apply:** Treat outbound DRS/product input and inbound PriceShape market data/advice as separate directions. Prefer preserving the current CSV contract while introducing Hub-selected costs, pending verification of the actual feed schema and API documentation.

The user wants DRS cost inputs routed through Pricing Hub, a Hub-generated CSV for PriceShape, a persistent product reference and separate PriceShape advice input for Channelmanager, and downloadable printer-price-adjustment workbooks. Writing prices back to DRS is deferred until the organization is ready.

**Why:** The user specified this operational sequence when supplying the two current input feeds and printer workbook.

**How to apply:** Keep uploads unchanged and create new exports. Connections must be explicitly activated before live processing; attaching a sample or saving settings is not activation. Keep the existing competitor feed independent and unchanged. Missing external fields remain configurable and unverified rather than invented.
