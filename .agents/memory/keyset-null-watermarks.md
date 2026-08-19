---
name: Keyset pagination & NULL watermarks
description: NULL watermark rows silently dropped by keyset pagination
---
Keyset pagination on (watermark, pk) silently skips rows whose watermark is NULL — NULL comparisons are never true.
**Why:** rows never updated (NULL updated_at) vanished from BigQuery export pages.
**How to apply:** COALESCE the watermark to epoch in both ORDER BY and the keyset comparison (including the bound :last_key parameter).
