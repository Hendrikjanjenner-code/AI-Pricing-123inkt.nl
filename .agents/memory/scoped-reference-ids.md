---
name: Cross-referenced ids must be shop-scoped
description: Client-supplied reference ids (evidence_id etc.) must be resolved within shop + owning entity before persisting.
---
Regel: elke schrijfroute die een client-geleverd id van een ander record accepteert (bijv. evidence_id) moet dat id via één centrale helper resolven met shop_id én de eigenaar-entiteit (bijv. competitor_name); onbekend of vreemd id → 400/404 vóór associatie. Geldt ook voor ids die in JSON-meta belanden (geen DB-FK!).
**Why:** completion code review wees taakwerk af omdat een PK-only evidence-lookup cross-tenant koppeling en orphan-referenties toeliet (social-media-guard omzeilbaar).
**How to apply:** bij nieuwe profiel-/evidence-achtige structuren: resolve_-helper in de service, gebruiken in álle writes incl. JSON field_meta-paden; tests voor foreign-shop, foreign-entity en niet-bestaand id.
