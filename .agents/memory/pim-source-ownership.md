---
name: PIM source ownership
description: Ownership/conflict policy for the product content layer
---
Rule: every field has an owning source (DRS/Leverancier/Handmatig/AI) and every stored value records its source. DRS-mastered fields are written only by the DRS sync — even when still empty — and every writer (supplier import, manual edit, AI approval) goes through one shared policy check: same-source updates OK, empty non-DRS fields OK, cross-source differences become explicit conflicts (warning or 409; AI proposals stay pending), never silent overwrites.
**Why:** DRS stays product master (§4); a foreign source claiming an empty DRS field would block master sync forever, and silent overwrites hide data conflicts. Code review rejects any writer that bypasses the shared policy.
**How to apply:** route every new writer of attribute values through the central ownership check; add regression tests for both an existing DRS value and an initially empty DRS field later filled by the master.
