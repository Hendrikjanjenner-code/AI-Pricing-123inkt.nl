---
name: Generic JSX arguments and preview instrumentation
description: Explicit component type arguments can pass TypeScript while breaking the instrumented Vite preview.
---

Prefer inferred generic component types in JSX rather than explicit type arguments where the component's props already determine its type.

**Why:** The preview's metadata instrumentation inserted attributes before an explicit JSX type argument, producing invalid JSX that Babel rejected with HTTP 500, although TypeScript and unit tests passed.

**How to apply:** For a generic table, use `<RowsTable rows={typedRows} ... />` instead of `<RowsTable<RowType> ... />`. When TypeScript passes but Vite reports syntax errors involving injected metadata, check this before changing application logic or disabling instrumentation.
