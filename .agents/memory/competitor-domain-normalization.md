---
name: Competitor domain normalization
description: Durable identity & scoping decisions for competitor names.
---

Competitor identity is the canonical domain (lowercase, no scheme/www/path). Every path that writes OR compares a competitor name must canonicalize first — including import-selection exclusion lists, which may hold older raw variants; compare both sides normalized.

**Why:** raw variants (https://www.x.nl vs x.nl) split one competitor into several, fragmenting scores, duplicating approvals, and silently bypassing stored exclusions.

**How to apply:** normalize before persisting or matching competitor names anywhere new; keep original spellings only as aliases. "Recent niet gezien" is shop-scoped and relative to the newest observation within that shop — never "today", never another shop.
