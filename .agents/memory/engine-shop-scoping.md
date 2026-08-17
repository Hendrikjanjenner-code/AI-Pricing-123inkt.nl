---
name: Engine shop-scoping
description: Scoping rule for analytics engines and their APIs in the multi-shop model
---
Rule: every engine and its API must be shop-scoped end-to-end — resolve an explicit or default shop_id (404 on unknown), filter all source queries by shop, persist shop_id on result rows and signals, and scope by-id reads/mutations so a foreign-shop id returns 404.
**Why:** shops are a data dimension; unscoped queries mix commercial data across shops and produce wrong results.
**How to apply:** aggregator tables supersede prior open rows per shop on each run; model-registry versions carry an immutable config JSON that engines resolve at run start so rollback restores real behavior.

**Uniekheid verschuiven:** een unieke sleutel versmallen of verbreden vereist dat ALLE oude uniekheids-handhavers in de live DB meebewegen; test-DB's die vers uit de ORM worden opgebouwd verbergen dit verschil.
