---
name: DRS daily sales semantics
description: Verified source interpretation and conservative identity rules for the wide DRS daily report.
---

Keep business productcode, EAN and OEM separate from the stable technical product key. A PriceShape itemGroupId can identify multiple existing products; do not turn it into a unique identity or merge products solely on that value.

**Why:** Comparison of the supplied DRS report with the actual catalog exposed multi-product code matches and comma-separated EAN sets. Automatic single-code matching would attach sales to the wrong product.

**How to apply:** Resolve within the authorized shop, use EAN sets only to disambiguate, and block remaining conflicts. Preserve technical keys and history.

Reject repeated productcodes in a DRS catalog workbook, even when their EANs differ, before any catalog replacement or write.

**Why:** The catalog and hierarchy workflows are productcode-grained; accepting multiple EAN-specific rows for one code would make updates and hierarchy ownership ambiguous. Daily matching against an existing catalog is a separate, EAN-aware operation.

**How to apply:** Any future relaxation must redesign both catalog row identity and hierarchy resolution together, not just change the duplicate warning.

Import signed daily quantities and both supplied VAT amounts exactly. Return semantics are unverified: the user explicitly did not know whether returns had already been netted. Do not label these figures verified net sales or apply a second return adjustment. Current purchase prices and product-level margins are not historical daily costs.

**Why:** The supplied report contains negative daily values but no documented return treatment or historical daily cost fields. Inferring costs would manufacture historical profit.

**How to apply:** Disclose the uncertainty in preview; retain unknown historical cost/margin as unknown. Require an explicit report year because DD/MM headings omit it.