---
name: AI Gateway invariants
description: Durable security rules for the Copilot's AI Gateway (LLM boundary)
---
Rules for the LLM boundary:
1. Every string toward or from the external model passes the PII scrubber — user question, history, tool results, and the final answer before persistence. Coverage must include names, addresses, IBAN and BSN in free text, not just e-mail/phone.
2. Tool arguments from the model are allowlisted against the published schema; scope parameters (like `shop_id`) always come from the server-side session/conversation context, never from model output.
3. The model can only call the closed approved-function registry; new semantic functions must be shop-scoped (via DimProduct SKUs when the fact table lacks `shop_id`).

**Why:** the LLM is an untrusted input channel — prompt injection can request other tenants' data or echo PII; these invariants are the tenant-isolation and privacy boundary.

**How to apply:** when adding gateway tools or prompts, keep these three invariants and cover each with an adversarial test.

## Provider choice (persistent)
The active LLM provider is a DB-backed admin setting (singleton `AiProviderSetting`): explicit choice wins with no silent fallback; auto mode prefers Replit AI when `AI_INTEGRATIONS_OPENAI_*` are set, else `OPENAI_API_KEY`. Probe cache is per provider and resets on switch. `setupReplitAIIntegrations` is NOT available in task environments — provisioning the Replit AI env vars must happen from the main session; once provisioned, auto mode activates Replit AI without code changes.

## Reachability probe quirks
The Replit AI proxy rejects GET /models with 405, so a models.list() probe false-negatives. Probe falls back (Replit provider only) to a minimal chat completion; reasoning models can hit the tiny token budget and return 400 "output limit reached" — that specific 400 counts as reachable (auth + routing proven). For openai_direct, 404/405 stays a failure.
