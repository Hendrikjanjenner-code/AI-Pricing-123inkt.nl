# AI Gateway — provider-dataflow & privacy (§31/§32)

## Architectuur

```
Gebruiker (Copilot-chat)
   │  vraag (Nederlands)
   ▼
AI Gateway (ai_gateway.py) — ENIGE plek met LLM-toegang
   1. Intent-detectie ......... LLM kiest approved tools (function calling)
   2. Autorisatie ............. rol van gebruiker vs. required_roles per functie
   3. Approved functions ...... uitsluitend SEMANTIC_FUNCTIONS (semantic_layer.py)
   4. Semantic layer .......... shop-scoped, metric-gestandaardiseerde queries
   5. PII-filter .............. pii_scrub() op ALLE tool-resultaten richting model
   6. Geaggregeerd resultaat .. alleen totalen/scores, geen ruwe klantdata
   7. LLM ..................... eindantwoord als gestructureerd JSON
   ▼
Antwoord: conclusion · period · sources · data_freshness · records ·
          confidence · limitations · warnings · suggested_action · links
```

## Provider

- **Provider:** Replit AI Integrations (OpenAI-compatibele proxy).
  Configuratie via `AI_INTEGRATIONS_OPENAI_BASE_URL` + `AI_INTEGRATIONS_OPENAI_API_KEY`
  (automatisch door Replit gezet; geen eigen API-key nodig). Expliciete
  fallback: `OPENAI_API_KEY` rechtstreeks naar OpenAI.
- **Model:** instelbaar via `AI_COPILOT_MODEL` (default `gpt-5.1`).
- **Datastroom naar de provider:** systeem-prompt, de gebruikersvraag,
  gespreksgeschiedenis (max. 12 berichten) en PII-gescrubde, geaggregeerde
  tool-resultaten. Er gaat **nooit** ruwe klantdata, vrije SQL of een
  databaseverbinding richting het model.

## Privacy-controles (§31)

- `pii_scrub()` werkt in twee lagen: (1) een key-denylist die velden als
  e-mail, naam, telefoon, adres en wachtwoord/tokens volledig weglaat uit
  gestructureerde data, en (2) een vrije-tekst-detector die e-mailadressen,
  telefoonnummers, IBAN's, BSN's (elfproef), postcodes, straat+huisnummer
  en via aanhef/zelfintroductie herkenbare persoonsnamen maskeert.
  Ook het eindantwoord van het model wordt gescrubd vóór weergave en
  opslag (tegen geëchode PII).
- De filter draait op **alle** tekst richting het model: tool-resultaten,
  de gebruikersvraag én de gespreksgeschiedenis. Vragen worden bovendien
  al bij binnenkomst gemaskeerd, zodat ook de opgeslagen gespreks-
  geschiedenis (ai_messages, gesprekstitels) geen e-mail-/telefoonpatronen
  bevat — er wordt dus geen ruwe PII-chat bewaard.
- `pseudonymous_customer_id` is het enige toegestane klant-identificerende
  veld (het platform kent geen andere persoonsgegevens per §31).
- Loyalty-/klantdata wordt alleen geaggregeerd via semantic-layer-functies
  ontsloten; er is geen tool die individuele klantrecords teruggeeft.

## Governance

- **Geen vrije SQL (§64.8):** het model kan uitsluitend de gesloten lijst
  `SEMANTIC_FUNCTIONS` aanroepen; onbekende functienamen worden geweigerd.
- **Geen autonome uitvoering (§64.7):** alle tools zijn read-only;
  `simulate_price_change` is een pure simulatie en zet niets klaar.
- **Logging (§32):** elke gateway-call → `ai_model_calls` (gebruiker, rol,
  model, functies+argumenten, databronnen, timestamp, doel, tokens,
  duur, status) en `cost_usage_records` (usage_type `ai_call`).
  Inzien: `GET /api/copilot/model-calls` (analyst en hoger).
- **Fail-safe (§56):** zonder of met falende LLM-provider blijft de
  applicatie volledig werken; de Copilot geeft dan een gestructureerd
  foutantwoord met warning, nooit een 500.
