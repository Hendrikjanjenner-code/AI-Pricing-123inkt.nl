---
name: Data quality issue registry
description: How §30 quality detections persist with workflow state
---
Quality detections are stateless scans; workflow state (owner/status) lives in a separate registry table keyed by a stable `issue_code`, upserted on every scan.

**Why:** detections re-run constantly; only a code-keyed upsert keeps owner/status stable across scans, auto-resolves issues that disappear (count→0) and reopens resolved ones that return.

**How to apply:** never store workflow fields on computed results; when adding a detection, give it a stable unique code and severity/impact/action text — the registry sync handles the rest.
