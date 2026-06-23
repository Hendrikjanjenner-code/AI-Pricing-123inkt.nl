---
name: Traffic model fields
description: FactTrafficDaily uses entity_type/entity_id, not sku_id.
---

## Rule
`FactTrafficDaily` (`fact_traffic_daily`) stores data for both SKUs and categories.  
- `entity_type` = "SKU" or "CATEGORY"  
- `entity_id` = the sku_id or category name  

There is no `sku_id` column directly on this model.

**Why:** The table was designed to be generic across entity types.

**How to apply:** When writing traffic data for a SKU from CSV import, always set `entity_type="SKU"` and `entity_id=sku_id`.
