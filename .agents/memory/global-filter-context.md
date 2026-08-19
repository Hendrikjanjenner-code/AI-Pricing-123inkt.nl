---
name: Global Filter Context
description: How the universal hierarchy/brand filter context works and how to hook more endpoints/screens onto it.
---

Rule: dashboards join the global filter context by (1) rendering GlobalFilterBar, (2) appending `apiFilterParams(useGlobalFilters())` to their fetch URLs **and query keys**, and (3) the backend endpoint accepting `hierarchy_node_ids`/`brands` csv params via `routes/global_filters.resolve_sku_filter` (returns None = no filter, empty set = match nothing — never treat empty set as "no filter").

**Why:** parent-selection must expand to descendants server-side (prefix-LIKE on the materialized node path); client only prunes redundant descendant selections. Store (module singleton + sessionStorage) is the source of truth because wouter navigation drops query params; `useFilterUrlSync` rewrites `f_hn/f_brand/f_days/f_sku` after each location change so deep links stay shareable. URL params win over stored state on load.

**How to apply:** when migrating more engines (follow-up task), add the two Query params + `resolve_sku_filter` intersection with the endpoint's existing shop-scoped sku list, and on the page use the dashboard/competition pages as reference. `periodDays`/`skuQuery` are client-side/context-only until endpoints support them.
