---
name: Competitor domain normalization
description: Durable identity & scoping decisions for competitor names.
---

Competitor identity is the canonical domain (lowercase, no scheme/www/path), produced by one central normalize helper. Any new write path that stores a competitor name must go through it; original spellings survive only as aliases.

**Why:** raw feed/upload variants (https://www.x.nl vs x.nl) previously split one competitor into several, fragmenting scores and duplicating discovery approvals.

**How to apply:**
- New code paths that persist competitor names must normalize first — tests assume canonical lowercase names.
- Merging or deleting a competitor registry row requires repointing every FK reference first (discover them via mapper metadata, never a hand-kept list) or FK constraints break startup.
- "Recent niet gezien" is shop-scoped and relative to the newest observation within that shop — never "today", never another shop.
