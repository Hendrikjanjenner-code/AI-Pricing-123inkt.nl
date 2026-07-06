---
name: Frontend global 15s fetch timeout
description: The pricing-engine patches window.fetch with a 15s AbortSignal; slow calls must opt out.
---

# Global 15s fetch timeout (pricing-engine frontend)

`src/lib/fetch-timeout.ts` monkey-patches `window.fetch` at startup so EVERY raw
`fetch()` without its own `signal` gets `AbortSignal.timeout(15_000)`.

**Why it matters:** any legitimately slow request (e.g. connector "test verbinding"
or "sync" that hits a slow/large external feed) is aborted at 15s and surfaces as a
generic "Netwerkfout" in the page's `catch` — even when the backend eventually
returns 200. This is a false failure, not a real network error.

**How to apply:** for a call that can legitimately take longer than 15s, pass your
own `signal: AbortSignal.timeout(<ms>)` in the fetch init. The global patch checks
`if (init.signal)` and leaves such calls alone. (Connector test uses 60s, sync 300s.)
Do NOT raise the global default — it's a safety net against hung requests for the
rest of the app.
