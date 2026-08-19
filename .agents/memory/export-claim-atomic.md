---
name: Export dubbel-uitvoer-guard
description: Prijsexport/push claimt aanbevelingen atomisch; review eist race-safety
---
Rule: export/push paths must claim rows atomically (conditional UPDATE ... RETURNING on processing_status) BEFORE creating the job; filter the payload to claimed ids; release claims for safety-rejected lines and on failure.
**Why:** completion code review rejects post-hoc marking ("mark verwerkt after job creation") as not race-safe — two overlapping exports would both include the same line.
**How to apply:** any new "take pending rows and execute/export them" endpoint: claim-first + concurrent regression test (two parallel requests, exactly one non-dry-run line).
