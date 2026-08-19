---
name: Rebase drops adjacent module-level blocks
description: Task-merge rebases can silently drop module-level constant/comment blocks that sit between functions; verify definitions after every rebase.
---
The automated task-merge rebase resolves "interstitial" conflicts (code between two functions) with low confidence and can silently drop a module-level constants block that your code still references, producing NameErrors only at runtime/review.

**Why:** a full-sync constants block in a routes module was dropped twice during rebases; validation passed typecheck-free (Python) and failed only in review/runtime.

**How to apply:** after any rebase completes, grep the touched modules for every constant/helper your diff references (definitions, not just usages) before re-running validation.
