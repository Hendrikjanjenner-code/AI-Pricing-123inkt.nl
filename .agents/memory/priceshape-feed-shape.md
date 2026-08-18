---
name: PriceShape feed shapes (JSON + wide CSV)
description: The real PriceShape export-feed structures (JSON with nested vendors[], and the wide CSV of the default feed) and how competitor prices must be un-nested.
---

# Default feed = WIDE CSV, no gtin

The built-in default export feed (`public.app.priceshape.io/.../export/...`, ~13 MB)
returns **text/csv**, NOT JSON: one product per row, **no gtin/ean column**
(`itemGroupId` is the product key), decimal commas, and competitors as wide column
groups `vendor_N <field>` (domain, price, stockStatus e.g. "InStock", productUrl,
priceWithShipping, previousPrice, shippingCost, source, pricePosition, quantity) up
to N=50. The CSV parser lowercases headers → keys like `vendor_1 domain`. Ingest
un-nests these into per-competitor rows, dedupes offers on (sku, lowercased domain)
across the whole feed (first occurrence wins), and leaves `ean` NULL — never invent
an EAN. Unmapped fields go loss-free into raw_attributes.

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

**Server-side buffering:** the PriceShape export endpoint buffers the WHOLE feed
before sending the first byte — so even a streamed 5 MB sample waits ~18s for the
first byte. The connection *test* therefore streams only a bounded sample and parses
it tolerantly (partial/truncated JSON) instead of downloading the full feed; the real
sync still pulls everything. Don't expect a "test" to be instant — it's gated by
their first-byte latency, not by transfer size.
