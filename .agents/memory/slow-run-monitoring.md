---
name: Slow-run monitoring of nightly engines
description: How engine_slow_run bewaking must treat shop-scoped runs and rounded timings
---
Rule: forecast/decision (and other per-shop engines) run per shop in scheduled_engines.py — the shop-scoped run IS the production path. Slow-run monitoring must publish a shop-scoped engine_slow_run signal (shop_id + entity_id = shop id) instead of exempting scoped runs; disable via threshold <= 0. Only truly global full-catalog engines (pricing, traffic, competition-intelligence run_all) treat scoped runs as test-only.

**Why:** an earlier implementation exempted all scoped runs; code review rejected it because every scheduled production run was then unmonitored.

**How to apply:** reuse engine/run_profiling.py (RunProfiler + check_slow_run). Round total_seconds to 6 decimals, not 3 — with mocked-out steps a run rounds to 0.0 and a tiny test threshold can never trigger (tests use threshold 1e-9 + FastDB query stubs, see tests/test_engine_slow_run.py).
