---
name: Data-quality scan pipeline
description: Single consolidated pipeline for the periodic data-quality scan and its alert layers.
---
The scan has ONE pipeline: scheduler loop / one-shot (data_quality_scheduler) → ImportJob-wrapper + notificatielaag (data_quality_scan_scheduler.run_scan_once/_notify_issue, in-app + e-mail/webhook) → kern (data_quality_scan.run_quality_scan: detecties, registry, IntelligenceSignals, scan-run audit).

**Why:** duplicate scan schedulers cause double scans/alerts and divergent behavior on the shared database.

**How to apply:** never add a second scan/scheduler entry point; extend run_quality_scan (core) or _notify_issue (alert channels). One-shot mode must import `models` before create_all or the standalone process has no tables registered. Alert policy: every new issue alerts (any severity), reopened always alerts, open issues re-alert only when worsening (escalated to error, or error count grew).
