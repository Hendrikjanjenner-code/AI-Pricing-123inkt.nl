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


# ─── Antwoordstructuur ───────────────────────────────────────────────────────

ANSWER_KEYS = [
    "conclusion", "period", "sources", "data_freshness", "records",
    "confidence", "limitations", "warnings", "suggested_action", "links",
]

SYSTEM_PROMPT = """Je bent de Commercial AI Copilot van het AI Pricing & Commercial Intelligence Platform.
Je beantwoordt vragen van commerciële gebruikers (Nederlands) over pricing, marge, concurrentie, huismerk, promoties, traffic, inkoop en kansen.

Regels:
- Je mag UITSLUITEND data gebruiken die je via de aangeboden tools ophaalt. Verzin nooit cijfers.
- Roep eerst de relevante tool(s) aan; combineer meerdere tools waar nodig.
- Voor what-if-prijsvragen gebruik je simulate_price_change (change_pct als fractie, +3% = 0.03). Je voert NOOIT een prijswijziging uit — je simuleert alleen.
- Als een tool 'data_available': false teruggeeft, zeg dat eerlijk ("data unavailable") en benoem dat als limitation.
- Antwoord altijd in het Nederlands, zakelijk en concreet.

Als je klaar bent met tools, geef je je eindantwoord als JSON-object met exact deze velden:
{
  "conclusion": "kernconclusie in 2-6 zinnen, met concrete cijfers uit de tooldata",
  "period": "gebruikte periode, bv. 'laatste 30 dagen' of run-datum",
  "confidence": 0.0-1.0 (jouw inschatting van betrouwbaarheid op basis van datadekking),
  "limitations": ["beperkingen van dit antwoord"],
  "warnings": ["waarschuwingen, bv. ontbrekende data of lage confidence"],
  "suggested_action": "concrete vervolgactie voor de gebruiker (of null)",
  "links": [{"label": "modulenaam", "path": "/frontend-pad"}]
}
Beschikbare frontend-paden voor links: /prijsadviezen, /beslissingen, /producten, /signalen, /competition, /huismerk-impact, /promotie-intelligence, /procurement-forecast, /opportunities, /traffic-dashboard, /elasticiteit.
Geef ALLEEN het JSON-object, geen andere tekst."""


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


def run_copilot(
    db: Session,
    user: models.User,
    history: list[dict],
    question: str,
    conversation_id: Optional[int] = None,
    purpose: str = "copilot_question",
    shop_id: Optional[int] = None,
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

    client, provider = _make_client()
    if client is None:
        status = "unavailable"
        answer = _default_answer(
            "De AI-dienst is momenteel niet geconfigureerd. De rest van de applicatie "
            "werkt gewoon door; alle dashboards en modules blijven beschikbaar.",
            ["AI-integratie (Replit AI) is niet geconfigureerd — geen LLM-call uitgevoerd."],
            freshness,
        )
        yield {"type": "answer", "answer": answer}
        _log_call(db, user, conversation_id, purpose, provider or "none", calls_meta,
                  usage, roundtrips, started, status, "AI-provider niet geconfigureerd")
        return

    # PII-scrub op ALLE tekst richting het model (§31): ook de vraag en de
    # gespreksgeschiedenis kunnen door de gebruiker ingevoerde
    # persoonsgegevens bevatten (e-mail, telefoonnummer, ...).
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history[-MAX_HISTORY_MESSAGES:]:
        messages.append({"role": m["role"], "content": pii_scrub(m["content"])})
    messages.append({"role": "user", "content": pii_scrub(question)})
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
    for k in ANSWER_KEYS:
        answer.setdefault(k, None)

    # Belt-and-braces: ook het eindantwoord zelf wordt gescrubd vóór
    # weergave en persistentie (het model kan PII uit de vraag echoën).
    answer = pii_scrub(answer)

    yield {"type": "answer", "answer": answer}
    _log_call(db, user, conversation_id, purpose, provider, calls_meta, usage,
              roundtrips, started, status, error_message)


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
              error_message: Optional[str]) -> None:
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
