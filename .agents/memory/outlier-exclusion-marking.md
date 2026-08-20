---
name: Outlier exclusion marking
description: Competitor-price exclusions are marked on fact rows, never deleted; invariant for score reruns and new exclusion paths.
---

**Rule:** every path that excludes a competitor price from the reference price must mark the fact row (`excluded_reason` + optional `exclusion_detail` with `suspected_cause`) instead of silently skipping it. Score reruns first reset that day/shop's marks, then rewrite them.

**Why:** the CI dashboard once excluded thousands of prices silently; users could not tell whether it was justified or a data problem. The data-quality reconciliation section aggregates these marks — an unmarked exclusion path is invisible there.

**How to apply:** when adding a new exclusion rule to score_competition (or a similar engine), add a reason code in the competition engine, mark the fact rows, and check the DQ outliers endpoint still classifies it. The outlier threshold is user-configurable via the priceshape import settings ("outlier_threshold", fraction of the median, default 0.30) — never hardcode it in callers. Reconciliation endpoints must apply the effective shop-scope (user_allowed_shop_ids: explicit shop outside scope → 403; no shop → user's allowed set), never raw shop_id filtering.
