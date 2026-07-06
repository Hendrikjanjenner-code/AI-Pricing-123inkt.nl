---
name: PriceShape feed JSON shape
description: The real PriceShape export-feed JSON structure and how competitor prices must be un-nested.
---

# PriceShape output-feed (export URL) JSON shape

The PriceShape "feed URL" export (`.../api/2022-08/export/<id>`) returns a JSON
**array of one object per product**, NOT flat competitor rows. Each product object:

- `gtin` — the EAN. There is **no** `sku` and **no** `ean` key; matching must map `gtin` → EAN.
- `itemGroupId` — PriceShape's own product-group id, not our internal sku_id.
- Own prices: `priceExclVat`, `priceInclVat`, `costPriceExclVat`, `shippingPrice`, `vatPercent`.
- `vendors` — a **nested array of competitor offers**. Each vendor has `domain`
  (the competitor identity), `price` (incl. VAT, excl. shipping), `productUrl`,
  `VendorstockStatus`, `pricePosition`, etc. `name` is the competitor's own product
  title (NOT the competitor name — use `domain`).

**Why it matters:** the importer expects flat one-competitor-per-row. A product must
be un-nested into N competitor rows (one per vendor) or every row fails to import.

**How to apply:** JSON parsing detects a nested vendor list (`vendors`/`competitors`/
`offers`/`merchants`/`sellers`/`listings`) and expands it — product scalars merged with
each vendor, vendor keys winning. Aliases wired: `gtin`→EAN, `domain`→competitor name,
`producturl`→url. Feed has no timestamp, so persist defaults the date to today.

**Scale:** a single real feed = ~197 MB / ~38k products → ~438k expanded competitor
rows across ~4.6k competitors. Download alone takes ~60s, so feed fetch uses a long
read timeout (see `_FEED_TIMEOUT`); health-checks stream only the first bytes.
