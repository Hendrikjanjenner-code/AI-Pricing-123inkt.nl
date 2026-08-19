---
name: DQ registry test isolation
description: How to test the data-quality registry/nightly scan without corrupting real registry rows in the shared dev DB.
---

Rule: in tests that drive `_sync_issue_registry` or `run_scan_once`, never replace the detection list wholesale (e.g. mock `_detect_issues` to return only a synthetic issue, or sync `[]`). The registry auto-resolves every issue missing from the list, so this silently flips real open issues to 'opgelost'.

**Why:** completion code review rejected tests that did exactly this — they invalidated existing data-quality workflow state and deleted foreign scheduler ImportJobs via `id > max` cleanup.

**How to apply:**
- Wrap the real `_detect_issues` and append one uniquely-coded synthetic issue; assert by filtering on that code.
- To simulate "resolved", update only the test row's status directly — never `_sync_issue_registry(db, [])`.
- Clean up ImportJobs by exact id, after verifying by content (unique code in warnings_json / unique error message) that the job was created by the test.
- Note: notifier rows are detached after the scheduler session closes — capture attributes at call time in the mock, not from stored row objects.
