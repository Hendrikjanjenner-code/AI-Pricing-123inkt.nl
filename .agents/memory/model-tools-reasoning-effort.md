---
name: Reasoning-model tool-calls op chat completions
description: gpt-5.6-terra weigert function tools met reasoning_effort op /v1/chat/completions
---
Nieuwere reasoning-modellen (gpt-5.6-terra) geven 400 "Function tools with reasoning_effort are not supported" op /v1/chat/completions; oudere modellen kennen reasoning_effort='none' juist niet.

**Why:** modelwissel via AI_COPILOT_MODEL brak de Copilot fail-safe ("LLM-storing") tot deze parameterretry bestond.

**How to apply:** de gateway heeft een wrapper die bij precies deze 400 opnieuw probeert met reasoning_effort='none'. Bij toekomstige modelwissels: smoke-test een tool-vraag, niet alleen de status-probe.
