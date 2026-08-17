---
name: Stale lib declarations break artifact typecheck
description: TS2305 "no exported member" from @workspace/* packages despite correct src exports
---
Artifact tsconfigs reference lib packages (composite, emitDeclarationOnly → dist). When the generated client (lib/api-client-react) changes, per-artifact `tsc --noEmit` resolves stale dist d.ts and reports TS2305 for members that exist in src.

**Why:** project references consume built declarations, not src.
**How to apply:** run root `pnpm run typecheck:libs` (tsc --build) first, then the artifact typecheck. Don't hand-edit generated client code.
