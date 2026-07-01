---
name: Paper_Copy import routes
description: Route prefix and request-shape quirks for the Paper_Copy XLSX import endpoints (distinct from the two-tab DRS importer).
---

Paper_Copy import endpoints live under prefix `/api/uploads/paper-copy/...` (not `/api/paper-copy/...`), grouped with the other CSV upload types even though it's a single-sheet XLSX importer.

- `POST /validate` and `POST /save` both take the file as multipart `file` upload — `save` is NOT job_id-based, it re-parses the uploaded file each time (mirrors the DRS uploader pattern).
- `DELETE /all` (admin-only) takes `confirm_phrase` as a Form field (not JSON body) and requires it to exactly match a hardcoded phrase constant.

**Why:** matches the existing DRS/CSV upload route conventions in this codebase, so a naive route guess (e.g. `/api/paper-copy/jobs` or job_id-based save) will 404 or 422.

**How to apply:** when adding smoke tests or new client code against Paper_Copy import, always confirm the router's `prefix=` in `routes/paper_copy.py` first, and send file uploads as multipart form-data, not JSON.

## Upsert keying and validation gate

Upsert-by-productcode must resolve existing `DimProduct` rows by `sku_id` globally, not scoped to `category == "Paper_Copy"` — a productcode could already exist under a different category (e.g. imported by another feed), and a category-scoped lookup would treat it as new and attempt an INSERT with a duplicate PK. Always query existing rows by `sku_id.in_(productcodes_in_file)` across all categories, then explicitly reassign `category` on update. Keep a separate category-scoped query only for "replace mode" deletion of stale rows.

The "can import" gate must require zero hard validation errors (`len(errors) == 0`), not just "at least one valid row" — otherwise files with some invalid rows (bad numbers/dates) still pass and partially import bad data.

**Why:** both bugs were caught by code review after being missed in initial manual testing (single-file happy-path only masked them).

**How to apply:** whenever building an XLSX/CSV import with upsert-by-natural-key semantics in this codebase, test the cross-category collision case explicitly (create the key under a different category first, then re-import) and test at least one row with a hard error to confirm the whole import is blocked, not partially applied.
