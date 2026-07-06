---
name: Bash sandbox background processes
description: Long-running background jobs launched from the bash tool do not survive after the call returns.
---

Backgrounded processes (`nohup ... &`) started in the `bash` tool do **not** persist
after the tool call returns in this sandbox — they get cleaned up. Their log files
stay empty and no DB writes land.

**Trap:** polling with `pgrep -f <script>.py` gives a *false positive* "still running"
because the pattern matches the bash command **itself** (the poll command's own line
contains the script name). Tell-tale sign: the matched PID **increments** each poll and
RSS is tiny (2–3 MB) — that's a fresh short-lived shell, not your job.

**How to run long jobs instead:**
- For a slow download: fetch to disk first with `curl` in the foreground (measure with
  `-w "size=%{size_download} time=%{time_total}s"`, bound with `timeout`/`--max-time`),
  then process from the file in separate fast steps that each fit the ~120s tool limit.
- Or drive it through an already-running workflow/server endpoint.
- Or split the pipeline into phases (parse+insert, score, engine) run as separate
  foreground calls.

**Why:** the ~206MB PriceShape feed pipeline appeared to "run in the background" for
minutes while doing nothing; the job had actually died instantly.
