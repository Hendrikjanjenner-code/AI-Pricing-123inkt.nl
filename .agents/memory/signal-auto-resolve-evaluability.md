---
name: Signal auto-resolve evaluability
description: Rules for auto-resolving intelligence signals without falsely closing unevaluated conditions
---

Auto-resolve of intelligence signals must be scoped to what was *actually evaluated* this run — per entity AND per signal type.

**Why:** Completion reviews rejected coarser versions repeatedly: shop-level "any data present" gates falsely resolve signals for SKUs with insufficient history, promos without sales data, unscored loyalty members, or source-dependent risks (competitor/supplier) whose feed is absent. "No data" and "not evaluated" are never the same as "condition fixed".

**How to apply:**
- `auto_resolve_signals` accepts `entity_ids` (evaluated-entity scope) plus `signal_types`; pass both.
- Forecast: track evaluated SKUs per risk type — stock/demand/margin when fc30 exists; competitor only when a *shop-scoped* SkuCompetitionScore exists; supplier only when a supplier record with lead time exists.
- Promotion: only SKUs whose promos were ALL analyzable.
- Loyalty: NBA scope = scored members (condition over ALL qualifying scores, not the published top-50); fraud scope = members with a fraud row for the run (any status); liability = per shop with loyalty members, resolve when outstanding points hit 0.
- Regression tests must include mixed-data runs (one evaluable + one non-evaluable entity) and cross-shop source rows.
