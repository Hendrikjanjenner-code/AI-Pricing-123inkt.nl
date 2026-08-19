---
name: Full-suite validation vs moving main
description: Task completion reruns the full pytest suite after rebase onto main; unrelated merges can break it and block completion.
---
Task completion validation rebases onto main and runs the full api-server suite; failures from *other* freshly merged tasks block your task.

**Why:** Parallel tasks merge continuously; twice a merge left a constant referenced but never defined (`FTS_MIN_RANK` in few-shot FTS, `ED_PFX` in elasticity tests) which only surfaced in the full run.

**How to apply:** When validation fails on tests you didn't touch, first check for NameError/undefined-constant bad merges and data-dependent tests (dev DB holds real feed/sync data — seeded "latest job" scenarios may not be the latest). Fix minimally or make the test skip when the scenario isn't measurable; note it in drift_reason.
