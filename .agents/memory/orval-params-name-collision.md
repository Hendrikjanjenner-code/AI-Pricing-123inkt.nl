---
name: Orval params name collision
description: Endpoints with both path- and query-params generate colliding exports in lib/api-zod.
---
When an openapi.yaml endpoint has BOTH path parameters and query parameters, orval's zod output emits a const `<OperationId>Params` (path params) while the types output emits a type `<OperationId>Params` (query params). The star re-exports in lib/api-zod/src/index.ts then fail typecheck with TS2308 "already exported a member".

**Why:** hit when adding a shop_id query param to a `/{name}` detail endpoint; existing endpoints only ever had one of the two, so the quirk was invisible.

**How to apply:** resolve by adding an explicit `export { <Name> } from "./generated/api";` line in the handwritten lib/api-zod/src/index.ts (explicit exports win over star exports), or avoid combining path + query params on one operation.
