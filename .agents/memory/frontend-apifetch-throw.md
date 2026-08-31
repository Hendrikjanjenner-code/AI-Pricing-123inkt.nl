---
name: Page-local fetch helpers must throw on !ok
description: React Query caches error payloads as data when a fetch helper returns r.json() without checking r.ok
---
The rule: any page-local `apiFetch`-style helper must check `r.ok` and throw, never `return r.json()` unconditionally.

**Why:** during task-#318 e2e testing, a 500 JSON body (`{detail: ...}`) was cached by React Query as "data"; the UI rendered misleading empty states and "geen afzetdata" tiles while the API was actually fine on retry — invisible failure, hard to diagnose.

**How to apply:** when adding queries to pricing-engine pages, throw on non-2xx and wire `isError` into a visible error state per card. Competition page (`competition-competitors.tsx`) is the reference pattern.
