---
name: Upload warning caps vs structural warnings
description: ImportJob warnings_json/error_log are capped; structural warnings must be pinned first.
---
_process_upload in routes/uploads.py caps persisted warnings (warnings_json[:50], error_log[:100]). Structural warnings such as "Onbekende kolommen ..." must be sorted to the front before persisting, or many row-level warnings (duplicates) silently push them out of the job log.

**Why:** completion code review rejected an unknown-columns feature because 100+ duplicate warnings evicted the structural warning from the persisted log.

**How to apply:** any new processor warning that must be auditable in ImportJob should either use the existing prioritization (prefix-based reorder in _process_upload) or be persisted separately; add a >cap regression test.
