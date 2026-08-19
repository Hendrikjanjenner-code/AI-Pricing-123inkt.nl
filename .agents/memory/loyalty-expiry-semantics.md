---
name: Loyalty expiry semantics
description: Product decision on overdue points and per-shop expiry policy in the loyalty engine
---
- Overdue-but-not-yet-expired points count as "expiring soon" in both liability figures and expiring_soon_members (they fall at the next expiry run). Tests must not assume they are excluded.
- Expiry policy is per shop; apply_expiry_run applies each member's shop policy but must keep the legacy summary fields expiry_cutoff/expiry_months (based on the scoped or default shop) — consumers rely on them.
**Why:** two parallel merges once shipped contradictory tests (include vs exclude overdue points); the newer include-semantics won.
**How to apply:** when touching loyalty expiry/liability code or tests, keep both surfaces consistent with include-semantics.
