"""
AI Gateway (masterprompt §32) — de ENIGE plek waar het externe LLM wordt
aangeroepen. Kernprincipes:

- Intent-detectie + tool-calling beperkt tot de approved SEMANTIC_FUNCTIONS
  uit de semantic layer — nooit vrije SQL (§64.8).
- Autorisatie: elke tool-call valideert de rol van de gebruiker tegen de
  required_roles van de semantische functie.
- PII-filter: alle data richting het model wordt gescrubd op
  persoonsgegevens (§31); alleen pseudonieme id's zijn toegestaan.
- Logging: elke gateway-call wordt vastgelegd in AiModelCall (gebruiker,
  model, functies, databronnen, timestamp, doel, tokenverbruik) én in
  CostUsageRecord (ai_call) voor het kostendashboard (§37).
- Fail-safe (§56): als het LLM niet beschikbaar is blijft de applicatie
  werken; de Copilot geeft dan een net, gestructureerd foutantwoord.
- De AI voert NOOIT zelfstandig beslissingen uit (§64.7): alle tools zijn
  read-only of pure simulaties.

Provider-dataflow: zie docs/ai-gateway.md.
"""
import json
import logging
import os
import re
import time
from datetime import date, datetime
from typing import Generator, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from semantic_layer import SEMANTIC_FUNCTIONS

logger = logging.getLogger("uvicorn.error")

AI_MODEL = os.environ.get("AI_COPILOT_MODEL", "gpt-5.1")
MAX_TOOL_ROUNDS = 6
MAX_HISTORY_MESSAGES = 12
LLM_TIMEOUT_SECONDS = 90


# ─── Provider-configuratie (Replit AI Integrations, geen eigen key) ─────────

def _provider_config() -> Optional[dict]:
    """Replit AI-integratie eerst; OPENAI_API_KEY als expliciete fallback."""
    base = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
    key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
    if base and key:
        return {"base_url": base, "api_key": key, "provider": "replit_ai_openai"}
    direct = os.environ.get("OPENAI_API_KEY")
    if direct:
        return {"base_url": None, "api_key": direct, "provider": "openai_direct"}
    return None


def ai_available() -> bool:
    return _provider_config() is not None


def _make_client():
    cfg = _provider_config()
    if not cfg:
        return None, None
    from openai import OpenAI
    kwargs = {"api_key": cfg["api_key"], "timeout": LLM_TIMEOUT_SECONDS}
    if cfg["base_url"]:
        kwargs["base_url"] = cfg["base_url"]
    return OpenAI(**kwargs), cfg["provider"]


# ─── PII-filter (§31): geen persoonsgegevens richting het externe model ─────

# Sleutelnamen die nooit richting het model mogen (denylist op key-naam).
_PII_KEY_PATTERN = re.compile(
    r"(email|e_mail|phone|telefoon|full_name|first_name|last_name|voornaam|"
    r"achternaam|address|adres|street|straat|postcode|zip|iban|bsn|"
    r"password|hashed_password|token|api_key|secret)",
    re.IGNORECASE,
)
# Waarde-patronen in vrije tekst. Naast e-mail en telefoon worden ook IBAN,
# BSN (met elfproef), NL-postcodes, straat+huisnummer en via aanhef/zelf-
# introductie herkenbare persoonsnamen gemaskeerd (§31).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(\+31|0031|0)[\s-]?\d[\s-]?(\d[\s-]?){7,9}")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{8,30}\b")
_POSTCODE_RE = re.compile(r"\b\d{4}\s?[A-Z]{2}\b")
_STREET_RE = re.compile(
    r"\b[A-ZÀ-Ý][\wà-ÿ]*(?:straat|laan|weg|plein|gracht|kade|dijk|singel|hof|pad|"
    r"steeg|markt|boulevard|dreef|erf)\s+\d+[a-zA-Z]?(?:[\s-]?\d+)?\b")
# Persoonsnamen: aanhef (dhr./mevr./de heer/mevrouw) of zelfintroductie
# ("mijn naam is ...", "ik heet ...", "contactpersoon: ...") gevolgd door
# gecapitaliseerde woorden.
_NAME_RE = re.compile(
    r"(?:\b(?:dhr|mevr|mw|dr|ing)\.?\s+|\bde heer\s+|\bmevrouw\s+|"
    r"\b(?:mijn|zijn|haar|de|onze)\s+naam\s+is\s+|\bik\s+heet\s+|"
    r"\bcontactpersoon(?:\s+is|:)\s*)"
    r"(?:[A-ZÀ-Ý][\wà-ÿ]*(?:\s+(?:van|de|der|den|het|ter|te|v\.?d\.?))*\s*){1,4}",
    re.UNICODE)
_BSN_CANDIDATE_RE = re.compile(r"\b\d{9}\b")


def _bsn_mask(match: re.Match) -> str:
    """Maskeer 9-cijferige reeksen die de elfproef doorstaan (BSN)."""
    digits = match.group(0)
    total = sum(int(d) * w for d, w in zip(digits, (9, 8, 7, 6, 5, 4, 3, 2, -1)))
    return "[BSN verwijderd]" if total % 11 == 0 else digits


def _scrub_text(s: str) -> str:
    s = _EMAIL_RE.sub("[e-mail verwijderd]", s)
    s = _IBAN_RE.sub("[IBAN verwijderd]", s)
    s = _PHONE_RE.sub("[telefoonnummer verwijderd]", s)
    s = _BSN_CANDIDATE_RE.sub(_bsn_mask, s)
    s = _STREET_RE.sub("[adres verwijderd]", s)
    s = _POSTCODE_RE.sub("[postcode verwijderd]", s)
    s = _NAME_RE.sub("[naam verwijderd] ", s)
    return s


def pii_scrub(obj):
    """Recursief: verwijder PII-sleutels en maskeer PII-patronen in strings.

    Twee lagen (§31):
    1. Key-denylist: velden als email/naam/adres/wachtwoord worden volledig
       weggelaten uit gestructureerde data.
    2. Vrije-tekst-detector: e-mail, telefoon, IBAN, BSN (elfproef),
       postcode, straat+huisnummer en via aanhef/zelfintroductie herkenbare
       persoonsnamen worden gemaskeerd in elke stringwaarde.
    Het platform slaat zelf geen persoonsnamen/adressen op (§31 kent alleen
    pseudonymous_customer_id); deze detector beschermt vooral tegen PII die
    gebruikers zelf in vragen of geschiedenis typen.

    pseudonymous_customer_id (§31) is expliciet toegestaan — dat is het enige
    klant-identificerende veld dat het platform kent.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "pseudonymous_customer_id":
                out[k] = v
                continue
            if _PII_KEY_PATTERN.search(str(k)):
                continue  # sleutel volledig weglaten
            out[k] = pii_scrub(v)
        return out
    if isinstance(obj, list):
        return [pii_scrub(v) for v in obj]
    if isinstance(obj, str):
        return _scrub_text(obj)
    return obj


# ─── Tool-definities: 1-op-1 afgeleid van de approved semantic functions ────

_TOOL_PARAMETERS: dict[str, dict] = {
    "get_product_performance": {
        "type": "object",
        "properties": {
            "sku_id": {"type": "string", "description": "SKU-id van het product"},
            "days": {"type": "integer", "description": "Periode in dagen (default 30)"},
        },
        "required": ["sku_id"],
    },
    "get_category_performance": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Optionele categorienaam"},
            "days": {"type": "integer"},
            "limit": {"type": "integer"},
        },
    },
    "get_competitor_ranking": {
        "type": "object",
        "properties": {
            "sku_id": {"type": "string", "description": "Optioneel: alleen deze SKU"},
            "limit": {"type": "integer"},
        },
    },
    "get_price_position": {
        "type": "object",
        "properties": {"sku_id": {"type": "string"}},
        "required": ["sku_id"],
    },
    "get_customer_switching": {
        "type": "object",
        "properties": {"sku_id": {"type": "string"}, "limit": {"type": "integer"}},
    },
    "get_traffic_summary": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "Optioneel: SKU of categorie"},
            "days": {"type": "integer"},
        },
    },
    "get_active_signals": {
        "type": "object",
        "properties": {
            "engine": {"type": "string"},
            "severity": {"type": "string"},
            "entity_id": {"type": "string"},
            "limit": {"type": "integer"},
        },
    },
    "get_margin_erosion": {
        "type": "object",
        "properties": {"days": {"type": "integer"}, "limit": {"type": "integer"}},
    },
    "get_private_label_potential": {
        "type": "object",
        "properties": {"limit": {"type": "integer"}},
    },
    "get_promotion_effectiveness": {
        "type": "object",
        "properties": {"limit": {"type": "integer"}},
    },
    "get_supplier_risk": {
        "type": "object",
        "properties": {"limit": {"type": "integer"}},
    },
    "get_opportunities": {
        "type": "object",
        "properties": {"limit": {"type": "integer"}},
    },
    "simulate_price_change": {
        "type": "object",
        "properties": {
            "sku_id": {"type": "string"},
            "change_pct": {
                "type": "number",
                "description": "Prijswijziging als fractie: +3% = 0.03, -5% = -0.05",
            },
        },
        "required": ["sku_id", "change_pct"],
    },
    "simulate_competitor_scenario": {
        "type": "object",
        "properties": {
            "sku_id": {"type": "string"},
            "change_pct": {
                "type": "number",
                "description": "Eigen prijswijziging als fractie: +3% = 0.03, -5% = -0.05",
            },
            "assume_follow": {
                "type": "array", "items": {"type": "string"},
                "description": "Concurrenten die geforceerd volgen (volgkans 1.0)",
            },
            "assume_no_follow": {
                "type": "array", "items": {"type": "string"},
                "description": "Concurrenten die geforceerd NIET volgen (volgkans 0.0)",
            },
        },
        "required": ["sku_id", "change_pct"],
    },
}


def build_tools() -> list[dict]:
    tools = []
    for name, sem in SEMANTIC_FUNCTIONS.items():
        params = _TOOL_PARAMETERS.get(name, {"type": "object", "properties": {}})
        tools.append({
            "type": "function",
            "function": {"name": name, "description": sem.description, "parameters": params},
        })
    return tools


# ─── Data-versheid ───────────────────────────────────────────────────────────

def get_data_freshness(db: Session) -> dict:
    """Laatste datum per kernbron; onderdeel van elk Copilot-antwoord."""
    def _max(col):
        try:
            v = db.query(func.max(col)).scalar()
            return str(v) if v else None
        except Exception:
            return None
    return {
        "sales": _max(models.FactSalesDaily.date),
        "prices": _max(models.FactPriceDaily.date),
        "competitor_prices": _max(models.FactCompetitorPriceDaily.date),
        "traffic": _max(models.FactTrafficDaily.date),
        "signals": _max(models.IntelligenceSignal.observed_at),
    }

def get_active_prompt(db: Session) -> tuple[str, Optional[int], Optional[int]]:
    """Laad de hoogste PromptVersion voor de Copilot; seed v1 vanuit de
    ingebouwde SYSTEM_PROMPT als er nog geen versie bestaat.

    Returns (prompt_text, prompt_version_id, version)."""
    try:
        row = (db.query(models.PromptVersion)
               .filter(models.PromptVersion.module_key == PROMPT_MODULE_KEY,
                       models.PromptVersion.title == PROMPT_TITLE)
               .order_by(models.PromptVersion.version.desc())
               .first())
        if row is None:
            row = models.PromptVersion(
                module_key=PROMPT_MODULE_KEY, title=PROMPT_TITLE, version=1,
                prompt_text=SYSTEM_PROMPT, created_by="system",
                notes="Automatisch geseed vanuit de ingebouwde Copilot-systeemprompt.",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row.prompt_text, row.id, row.version
    except Exception as exc:
        logger.warning("PromptVersion laden mislukt, fallback op ingebouwde prompt: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return SYSTEM_PROMPT, None, None
def _default_answer(conclusion: str, warnings: list[str], freshness: dict) -> dict:
    return {
        "conclusion": conclusion,
        "period": None,
        "sources": [],
        "data_freshness": freshness,
        "records": 0,
        "confidence": 0.0,
        "limitations": [],
        "warnings": warnings,
        "suggested_action": None,
        "links": [],
    }


def _execute_tool(db: Session, user: models.User, name: str, arguments: dict,
                  shop_id: Optional[int] = None) -> tuple[dict, dict]:
    """Voer één approved semantische functie uit. Returns (result, callmeta).

    Argument-allowlisting: alleen parameters uit het gepubliceerde tool-schema
    worden doorgegeven; al het andere (m.n. een door het model geïnjecteerde
    `shop_id`) wordt verworpen. De shop-scope komt uitsluitend server-side
    uit de geautoriseerde request-context — nooit uit modeloutput.
    """
    sem = SEMANTIC_FUNCTIONS.get(name)
    allowed_keys = set(_TOOL_PARAMETERS.get(name, {}).get("properties", {}).keys())
    dropped = sorted(set(arguments) - allowed_keys)
    arguments = {k: v for k, v in arguments.items() if k in allowed_keys}
    meta = {"name": name, "arguments": arguments}
    if dropped:
        logger.warning("AI Gateway: niet-toegestane tool-argumenten verworpen "
                       "voor %s: %s", name, dropped)
        meta["dropped_arguments"] = dropped
    if sem is None:
        # Het model vroeg om een niet-bestaande/niet-goedgekeurde functie.
        return {"error": f"Functie '{name}' is niet goedgekeurd in de AI Gateway."}, meta
    t0 = time.time()
    try:
        result = sem.fn(db, user, shop_id=shop_id, **arguments)
    except HTTPException as exc:
        result = {"error": exc.detail, "status_code": exc.status_code, "data_available": False}
    except TypeError as exc:
        result = {"error": f"Ongeldige argumenten voor {name}: {exc}", "data_available": False}
    except Exception as exc:
        logger.warning("AI Gateway toolfout %s: %s", name, exc)
        result = {"error": "Interne fout bij het ophalen van deze data.", "data_available": False}
    meta["duration_ms"] = round((time.time() - t0) * 1000, 1)
    meta["records"] = result.get("records") if isinstance(result, dict) else None
    meta["data_source"] = result.get("data_source", "postgresql") if isinstance(result, dict) else None
    # PII-scrub op ALLES wat richting het model gaat (§31)
    return pii_scrub(result), meta

def build_messages(db: Session, user: models.User, history: list[dict],
                   question: str, system_prompt: Optional[str] = None,
                   history_summary: Optional[str] = None) -> list[dict]:
    """Bouw de berichtenlijst richting het model:
    systeemprompt (uit PromptVersion) + duurzaam geheugen + few-shot uit goed
    beoordeelde eerdere antwoorden + (samengevatte) historie + de vraag.
    Alles wordt PII-gescrubd (§31)."""
    if system_prompt is None:
        system_prompt, _pid, _v = get_active_prompt(db)
    messages = [{"role": "system", "content": system_prompt}]

    memory_block = get_memory_block(db, user)
    if memory_block:
        messages.append({"role": "system", "content": pii_scrub(memory_block)})

    examples = get_fewshot_examples(db, question)
    if examples:
        messages.append({"role": "system", "content": pii_scrub(_fewshot_block(examples))})

    # Lange gesprekken: samenvatting van oudere berichten i.p.v. hard afkappen
    if history_summary and len(history) > MAX_HISTORY_MESSAGES:
        messages.append({
            "role": "system",
            "content": pii_scrub("Samenvatting van het eerdere gesprek:\n" + history_summary),
        })
    for m in history[-MAX_HISTORY_MESSAGES:]:
        messages.append({"role": m["role"], "content": pii_scrub(m["content"])})
    messages.append({"role": "user", "content": pii_scrub(question)})
    return messages
def run_copilot(
    db: Session,
    user: models.User,
    history: list[dict],
    question: str,
    conversation_id: Optional[int] = None,
    purpose: str = "copilot_question",
    shop_id: Optional[int] = None,
    history_summary: Optional[str] = None,
) -> Generator[dict, None, None]:
    """
    Voer de volledige gateway-pipeline uit en yield events:
      {"type": "status", "message": ...}
      {"type": "tool", "name": ..., "records": ...}
      {"type": "answer", "answer": {...}}
    Faalt NOOIT hard: bij LLM-storing volgt een gestructureerd foutantwoord.
    """
    started = time.time()
    freshness = get_data_freshness(db)
    calls_meta: list[dict] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    roundtrips = 0
    status = "success"
    error_message = None
    answer = None

    # Prompt-lifecycle (§48): systeemprompt uit PromptVersion-governance
    system_prompt, prompt_version_id, prompt_version = get_active_prompt(db)

    client, provider = _make_client()
    if client is None:
        status = "unavailable"
        answer = _default_answer(
            "De AI-dienst is momenteel niet geconfigureerd. De rest van de applicatie "
            "werkt gewoon door; alle dashboards en modules blijven beschikbaar.",
            ["AI-integratie (Replit AI) is niet geconfigureerd — geen LLM-call uitgevoerd."],
            freshness,
        )
        answer["prompt_version_id"] = prompt_version_id
        answer["prompt_version"] = prompt_version
        yield {"type": "answer", "answer": answer}
        _log_call(db, user, conversation_id, purpose, provider or "none", calls_meta,
                  usage, roundtrips, started, status, "AI-provider niet geconfigureerd",
                  prompt_version_id=prompt_version_id)
        return

    # PII-scrub op ALLE tekst richting het model (§31): ook de vraag en de
    # gespreksgeschiedenis kunnen door de gebruiker ingevoerde
    # persoonsgegevens bevatten (e-mail, telefoonnummer, ...).
    messages = build_messages(db, user, history, question,
                              system_prompt=system_prompt,
                              history_summary=history_summary)
    tools = build_tools()

    try:
        yield {"type": "status", "message": "Vraag analyseren…"}
        for _round in range(MAX_TOOL_ROUNDS):
            resp = client.chat.completions.create(
                model=AI_MODEL,
                max_completion_tokens=8192,
                messages=messages,
                tools=tools,
            )
            roundtrips += 1
            if resp.usage:
                usage["prompt_tokens"] += resp.usage.prompt_tokens or 0
                usage["completion_tokens"] += resp.usage.completion_tokens or 0
                usage["total_tokens"] += resp.usage.total_tokens or 0
            msg = resp.choices[0].message

            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
                })
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    yield {"type": "status", "message": f"Data ophalen: {tc.function.name}…"}
                    result, meta = _execute_tool(db, user, tc.function.name, args,
                                                 shop_id=shop_id)
                    calls_meta.append(meta)
                    yield {"type": "tool", "name": tc.function.name,
                           "records": meta.get("records"), "data_source": meta.get("data_source")}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str)[:60000],
                    })
                continue

            # Geen tool-calls meer: dit is het eindantwoord
            raw = (msg.content or "").strip()
            answer = _parse_answer(raw)
            break

        if answer is None:
            answer = _default_answer(
                "Het maximum aantal analysestappen is bereikt zonder eindantwoord. "
                "Stel de vraag specifieker (bv. met een SKU of categorie).",
                ["Tool-limiet bereikt zonder afgerond antwoord."], freshness)
            status = "failed"
    except Exception as exc:
        logger.error("AI Gateway LLM-fout: %s", exc)
        status = "failed"
        error_message = str(exc)[:500]
        answer = _default_answer(
            "De AI-dienst is tijdelijk niet bereikbaar. Probeer het over enkele "
            "minuten opnieuw — alle overige modules blijven gewoon werken.",
            ["LLM-storing: het antwoord kon niet worden gegenereerd (§56 fail-safe)."],
            freshness,
        )

    # Verrijk het antwoord met gateway-metadata (bronnen, versheid, records)
    answer.setdefault("warnings", [])
    answer.setdefault("limitations", [])
    answer["sources"] = [
        {"function": m["name"], "data_source": m.get("data_source") or "postgresql",
         "records": m.get("records")}
        for m in calls_meta
    ]
    answer["data_freshness"] = freshness
    answer["records"] = sum(int(m.get("records") or 0) for m in calls_meta)
    if not calls_meta and status == "success":
        answer["warnings"].append("Dit antwoord is niet onderbouwd met platformdata (geen tool-calls).")
        answer["confidence"] = min(float(answer.get("confidence") or 0), 0.3)
    answer["prompt_version_id"] = prompt_version_id
    answer["prompt_version"] = prompt_version
    for k in ANSWER_KEYS:
        answer.setdefault(k, None)

    # Belt-and-braces: ook het eindantwoord zelf wordt gescrubd vóór
    # weergave en persistentie (het model kan PII uit de vraag echoën).
    answer = pii_scrub(answer)

    yield {"type": "answer", "answer": answer}
    _log_call(db, user, conversation_id, purpose, provider, calls_meta, usage,
              roundtrips, started, status, error_message,
              prompt_version_id=prompt_version_id)


def _parse_answer(raw: str) -> dict:
    """Parse het JSON-eindantwoord; val terug op platte tekst als conclusion."""
    text = raw
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("conclusion"):
            try:
                obj["confidence"] = max(0.0, min(1.0, float(obj.get("confidence") or 0)))
            except (TypeError, ValueError):
                obj["confidence"] = 0.0
            if not isinstance(obj.get("limitations"), list):
                obj["limitations"] = [str(obj["limitations"])] if obj.get("limitations") else []
            if not isinstance(obj.get("warnings"), list):
                obj["warnings"] = [str(obj["warnings"])] if obj.get("warnings") else []
            if not isinstance(obj.get("links"), list):
                obj["links"] = []
            return obj
    except json.JSONDecodeError:
        pass
    return {"conclusion": raw, "confidence": 0.3,
            "limitations": ["Antwoord kon niet volledig gestructureerd worden."],
            "warnings": [], "links": []}


def _log_call(db: Session, user: models.User, conversation_id: Optional[int],
              purpose: str, provider: str, calls_meta: list[dict], usage: dict,
              roundtrips: int, started: float, status: str,
              error_message: Optional[str],
              prompt_version_id: Optional[int] = None) -> None:
    """Log de gateway-call in AiModelCall + CostUsageRecord. Faalt stil-veilig."""
    duration_ms = round((time.time() - started) * 1000, 1)
    datasources = sorted({m.get("data_source") or "postgresql" for m in calls_meta}) if calls_meta else []
    try:
        db.add(models.AiModelCall(
            username=user.username, user_role=user.role,
            conversation_id=conversation_id, purpose=purpose,
            provider=provider, model=AI_MODEL,
            functions_called=calls_meta, datasources=datasources,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            llm_roundtrips=roundtrips, duration_ms=duration_ms,
            status=status, error_message=error_message,
            prompt_version_id=prompt_version_id,
        ))
        db.add(models.CostUsageRecord(
            usage_type="ai_call", module="copilot", username=user.username,
            endpoint="/api/copilot", duration_ms=duration_ms, ai_model=AI_MODEL,
            tokens_in=usage["prompt_tokens"], tokens_out=usage["completion_tokens"],
            quantity=1.0,
        ))
        db.commit()
    except Exception as exc:
        logger.warning("AI Gateway-logging mislukt: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass

def maybe_summarize_conversation(db: Session, user: models.User,
                                 conversation_id: int) -> None:
    """Vat oudere berichten van een lang gesprek samen (i.p.v. afkappen).
    Fail-safe: fouten worden gelogd, nooit doorgegeven."""
    try:
        msgs = (db.query(models.AiMessage)
                .filter(models.AiMessage.conversation_id == conversation_id)
                .order_by(models.AiMessage.id).all())
        if len(msgs) <= MAX_HISTORY_MESSAGES:
            return
        older = msgs[:-SUMMARY_KEEP_RECENT]
        existing = (db.query(models.AiConversationSummary)
                    .filter(models.AiConversationSummary.conversation_id == conversation_id)
                    .first())
        if existing and existing.upto_message_id == older[-1].id:
            return  # al actueel
        client, provider = _make_client()
        if client is None:
            return
        started = time.time()
        transcript = "\n".join(
            f"{m.role}: {pii_scrub(m.content or '')[:1000]}" for m in older)[:20000]
        prev = f"Bestaande samenvatting:\n{existing.summary}\n\n" if existing else ""
        resp = client.chat.completions.create(
            model=AI_MODEL, max_completion_tokens=1024,
            messages=[
                {"role": "system", "content":
                 "Vat het onderstaande Copilot-gesprek beknopt samen in het Nederlands "
                 "(max 10 zinnen): welke vragen zijn gesteld, welke conclusies en cijfers "
                 "zijn gegeven, en welke voorkeuren toont de gebruiker. Geen opmaak."},
                {"role": "user", "content": prev + transcript},
            ])
        summary = (resp.choices[0].message.content or "").strip()
        if not summary:
            return
        summary = _scrub_text(summary)
        if existing:
            existing.summary = summary
            existing.upto_message_id = older[-1].id
            existing.updated_at = datetime.utcnow()
        else:
            db.add(models.AiConversationSummary(
                conversation_id=conversation_id, summary=summary,
                upto_message_id=older[-1].id))
        db.commit()
        usage = {"prompt_tokens": (resp.usage.prompt_tokens or 0) if resp.usage else 0,
                 "completion_tokens": (resp.usage.completion_tokens or 0) if resp.usage else 0,
                 "total_tokens": (resp.usage.total_tokens or 0) if resp.usage else 0}
        _log_call(db, user, conversation_id, "conversation_summary", provider,
                  [], usage, 1, started, "success", None)
    except Exception as exc:
        logger.warning("Gesprekssamenvatting mislukt: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass

def maybe_extract_memory(db: Session, user: models.User,
                         conversation_id: int) -> None:
    """Extraheer duurzame voorkeuren/context uit het gesprek en sla ze op als
    AiUserMemory (upsert per key). Draait elke MEMORY_EXTRACT_EVERY vragen.
    Fail-safe: fouten worden gelogd, nooit doorgegeven."""
    try:
        user_msgs = (db.query(models.AiMessage)
                     .filter(models.AiMessage.conversation_id == conversation_id,
                             models.AiMessage.role == "user")
                     .order_by(models.AiMessage.id).all())
        if not user_msgs or len(user_msgs) % MEMORY_EXTRACT_EVERY != 0:
            return
        client, provider = _make_client()
        if client is None:
            return
        started = time.time()
        recent = user_msgs[-(MEMORY_EXTRACT_EVERY * 2):]
        transcript = "\n".join(f"- {pii_scrub(m.content or '')[:600]}" for m in recent)
        resp = client.chat.completions.create(
            model=AI_MODEL, max_completion_tokens=1024,
            messages=[
                {"role": "system", "content":
                 "Je destilleert DUURZAME voorkeuren en vaste context van een commerciële "
                 "gebruiker uit diens Copilot-vragen (bv. favoriete categorieën, vaste SKU's, "
                 "KPI-definitievoorkeuren, gewenste periodes). GEEN eenmalige vragen of "
                 "persoonsgegevens. Antwoord als JSON-array: "
                 '[{"key": "korte_snake_case_sleutel", "value": "waarde"}]. '
                 "Maximaal 5 items; lege array [] als er niets duurzaams is."},
                {"role": "user", "content": transcript},
            ])
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            items = []
        if not isinstance(items, list):
            items = []
        for it in items[:5]:
            if not isinstance(it, dict):
                continue
            key = str(it.get("key") or "").strip()[:200]
            value = _scrub_text(str(it.get("value") or "").strip())[:2000]
            if not key or not value or _PII_KEY_PATTERN.search(key):
                continue
            row = (db.query(models.AiUserMemory)
                   .filter(models.AiUserMemory.user_id == user.id,
                           models.AiUserMemory.key == key).first())
            if row:
                row.value = value
                row.source_conversation_id = conversation_id
                row.updated_at = datetime.utcnow()
            else:
                db.add(models.AiUserMemory(
                    user_id=user.id, key=key, value=value,
                    source_conversation_id=conversation_id))
        db.commit()
        usage = {"prompt_tokens": (resp.usage.prompt_tokens or 0) if resp.usage else 0,
                 "completion_tokens": (resp.usage.completion_tokens or 0) if resp.usage else 0,
                 "total_tokens": (resp.usage.total_tokens or 0) if resp.usage else 0}
        _log_call(db, user, conversation_id, "memory_extraction", provider,
                  [], usage, 1, started, "success", None)
    except Exception as exc:
        logger.warning("Geheugen-extractie mislukt: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass

def get_memory_block(db: Session, user: models.User) -> Optional[str]:
    """Bouw het geheugen-contextblok: voorkeuren van deze gebruiker plus
    organisatie-brede context (user_id NULL). None als er niets is."""
    try:
        rows = (db.query(models.AiUserMemory)
                .filter((models.AiUserMemory.user_id == user.id) |
                        (models.AiUserMemory.user_id.is_(None)))
                .order_by(models.AiUserMemory.updated_at.desc())
                .limit(MAX_MEMORY_ITEMS).all())
    except Exception:
        return None
    if not rows:
        return None
    lines = [f"- {r.key}: {r.value}" + (" (organisatie-breed)" if r.user_id is None else "")
             for r in rows]
    return ("Bekende voorkeuren en vaste context van deze gebruiker/organisatie "
            "(gebruik dit alleen als het relevant is voor de vraag):\n" + "\n".join(lines))

def get_fewshot_examples(db: Session, question: str,
                         limit: int = FEWSHOT_LIMIT) -> list[dict]:
    """Zoek eerder positief beoordeelde, vergelijkbare vragen+antwoorden
    (woordoverlap-similarity over recente positieve feedback)."""
    try:
        rows = (db.query(models.AiFeedback)
                .filter(models.AiFeedback.score > 0,
                        models.AiFeedback.question.isnot(None),
                        models.AiFeedback.answer_excerpt.isnot(None))
                .order_by(models.AiFeedback.created_at.desc())
                .limit(200).all())
    except Exception:
        return []
    scored = []
    for r in rows:
        sim = _similarity(question, r.question or "")
        if sim >= 0.25:
            scored.append((sim, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    seen: set[str] = set()
    out = []
    for _sim, r in scored:
        key = (r.question or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"question": r.question, "answer": r.answer_excerpt})
        if len(out) >= limit:
            break
    return out

def _fewshot_block(examples: list[dict]) -> str:
    parts = ["Eerder goed beoordeelde antwoorden op vergelijkbare vragen "
             "(alleen als stijl-/aanpakvoorbeeld — haal actuele cijfers ALTIJD "
             "opnieuw op via de tools):"]
    for ex in examples:
        parts.append(f"Vraag: {ex['question']}\nGoed beoordeeld antwoord: {ex['answer']}")
    return "\n\n".join(parts)

def get_history_summary(db: Session, conversation_id: int) -> Optional[str]:
    try:
        row = (db.query(models.AiConversationSummary)
               .filter(models.AiConversationSummary.conversation_id == conversation_id)
               .first())
        return row.summary if row else None
    except Exception:
        return None

def _similarity(a: str, b: str) -> float:
    wa = set(_WORD_RE.findall(a.lower()))
    wb = set(_WORD_RE.findall(b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)
