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
