---
name: External response diagnostics must be redacted
description: Lessons on surfacing external feed/sync failures safely (secrets redaction, no-migration status surfacing).
---

- **Rule:** any external response content (body previews, echoed URLs, error pages) must be redacted before it is logged, persisted, or shown in the UI — strip querystrings, credential-like key/value pairs, and long opaque tokens.
  **Why:** error pages and proxies echo the requested URL back, and feed URLs carry auth tokens; a "diagnostic preview" otherwise becomes a secrets leak visible to any user who can read import/status screens. A completion review rejected exactly this.
  **How to apply:** run previews through a redaction pass (see the redaction helpers next to the feed connector) before recording metadata; tests must assert token-like values never appear in errors/status/API responses.
- **Rule:** to surface background-sync failures in existing screens without a schema migration, reuse existing connector status columns via an atomic upsert on a fresh short session (the sync session may sit in an aborted transaction after the failure).
  **Why:** create_all won't add columns to existing prod tables; and writing status on the failed session silently no-ops.
