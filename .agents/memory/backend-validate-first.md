---
name: Backend validate-first uploads
description: Two-step upload flow — validate without saving, then import with the original File object.
---

## Rule
Upload flow is two-step:
1. `POST /api/uploads/validate?upload_type=<type>` — sends the File, returns a ValidationReport without saving anything.
2. `POST /api/uploads/<type>` — sends the original File object to actually import.

**Why:** Client-side CSV parsing with `split(",")` is brittle (breaks on quoted commas). The backend uses Python's `csv.DictReader` which handles RFC 4180 correctly. This also gives authoritative server-side validation before any data is committed.

**How to apply:** `data-upload.tsx` stores the `File` object from the input event and passes it directly to both calls. Do NOT reconstruct a Blob from text — always use the original File.
