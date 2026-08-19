---
name: Parallel task merges break full-suite validation
description: Why markTaskComplete validation fails on code you didn't write, and how to handle it
---
Completion validation runs the FULL api test suite against the rebased/merged state, so failures from sibling tasks land on your branch (e.g. a merge dropping a module-level constant, a test asserting an old API tuple shape, or two tasks changing the same regression test).

**Why:** several rounds of task #-completion were rejected purely due to other tasks' merged regressions (undefined constant after merge, 2-tuple unpack of a now 3-tuple API, CIS baseline vs old "influence==0" test).

**How to apply:** when validation fails, first check whether the failing tests touch your files at all; fix sibling regressions minimally to unblock (note it in drift_reason). After any rebase/merge, re-grep that your own module-level constants/imports survived — merges have silently dropped them. Full suite exceeds the 5-min shell timeout locally; run targeted test files instead and let validation run the rest.
