---
name: Price index direction
description: price_index = own_price / competitor_avg — the direction matters for advice text.
---

## Rule
`price_index = own_price / competitor_avg` (stored in `sku_competition_score`).

- `price_index < 1.0` → own price is **LOWER** than market (we're cheaper) → opportunity to increase margin
- `price_index ≈ 1.0` → well-positioned
- `price_index > 1.0` → own price is **HIGHER** than market (we're more expensive) → risk of losing volume

**Why:** An earlier implementation had the advice text inverted (< 1.0 said "boven markt" which is wrong).

**How to apply:** The thresholds in `routes/pilot.py` are: < 0.97 = "onder markt" (good), 0.97-1.01 = "goed gepositioneerd", 1.01-1.05 = "licht boven markt", > 1.05 = "significant boven markt".
