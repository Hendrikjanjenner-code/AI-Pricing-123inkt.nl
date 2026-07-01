---
name: Bounded "full" history lists need load-more, not a fixed cap
description: When a spec calls for a "volledige"/full history list but the backing API enforces a max limit, a single fixed-size fetch is not sufficient.
---

If a UI is specced to show "volledige importgeschiedenis" (full import history) or similar, and the backend query param has a max `limit`, don't just fetch once at a default page size and call it done — implement an incremental "load more" (or true pagination) that lets the user reach the backend's max limit, with a visible indicator of how many records are loaded vs. the cap.

**Why:** Code review rejected a page that fetched history with a hardcoded `limit=200` as not satisfying "volledige" (full) history — a fixed low cap silently hides older records with no way for the user to see them or know more exist.

**How to apply:** When a spec uses words like "full", "complete", "volledige", or "all" for a list that has a bounded API, add a client-side "load more" control that increases the requested limit up to the API's max, and show a status line (e.g. "N of M loaded, limit reached — filter to narrow further") so truncation is visible rather than silent.
