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

The supplied Product feed is a product/current-sale-price reference, not a verified PriceShape advice export. The supplied CostPrice sample contains final costs, not all purchase-price sources. The printer workbook's pre/post sheets are empty, so its lookup columns are provisional, not a verified DRS import contract.

**Why:** Treating these samples as complete operational contracts would silently substitute current prices for advice or invent missing purchase costs.

**How to apply:** Require a separately mapped advice source and an enriched cost source for actual calculations. Keep the original reference files importable without claiming they supply those missing fields. Confirm PriceShape's supported machine-feed authentication before treating a generated private feed URL as an operational external connection.

Readback accepts a full post-change price snapshot, but asserts only the non-suppressed targets of the exact exported workbook. Unchanged products outside that export are informational, not mismatches.

**Why:** A full DRS readback naturally contains unchanged products and zero-price channels that were deliberately excluded from the export.

**How to apply:** Missing or different exported targets must block confirmation; unrelated rows must not. Shop authorization and numeric validation still apply to the entire input.

The user wants Kabelshop.nl, Sneltoner.nl, Printabout.nl and Tonershop.nl as the standard channels, using the supplied SiteMinder-style channel list as the reference.

**Why:** The user explicitly named these four shops and supplied the channel-list screenshot.

**How to apply:** Treat these as the intended channel choices, not evidence that integrations are already connected or that Kabelshop should replace an existing printer-workbook label.
