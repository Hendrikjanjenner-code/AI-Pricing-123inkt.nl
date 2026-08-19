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
from datetime import date, datetime, timezone
from typing import Generator, Optional

from fastapi import HTTPException
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from database import SessionLocal

import models
from semantic_layer import SEMANTIC_FUNCTIONS

logger = logging.getLogger("uvicorn.error")

AI_MODEL = os.environ.get("AI_COPILOT_MODEL", "gpt-5.1")
MAX_TOOL_ROUNDS = 6
MAX_HISTORY_MESSAGES = 12
SUMMARY_KEEP_RECENT = 4   # laatste N berichten niet meenemen in samenvatting (behoud context)
LLM_TIMEOUT_SECONDS = 90
FEWSHOT_LIMIT = 5        # max aantal few-shot voorbeelden uit positieve feedback
MAX_MEMORY_ITEMS = 20    # max AiUserMemory-regels in context
MEMORY_EXTRACT_EVERY = 5 # na elk N-de user-bericht geheugen opslaan

PROMPT_MODULE_KEY = "copilot"
PROMPT_TITLE = "Copilot Systeemprompt"

# Regex voor woordoverlap-similarity in few-shot retrieval
_WORD_RE = re.compile(r'\w+')

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

# ─── Prompt-governance ────────────────────────────────────────────────────────
PROMPT_MODULE_KEY = "copilot"
PROMPT_TITLE = "Copilot Systeemprompt"
SYSTEM_PROMPT = (
    "Je bent de AI Pricing Copilot van dit commercieel-intelligence platform. "
    "Je helpt commerciële teams met prijsanalyse, concurrentiebeelden en besluit-"
    "ondersteuning op basis van platformdata. "
    "Antwoord altijd in het Nederlands, beknopt en cijfermatig onderbouwd. "
    "Je roept alleen goedgekeurde tools aan (semantic functions) — je voert "
    "nooit zelfstandig prijswijzigingen of andere mutaties uit. "
    "Als data ontbreekt of onzeker is, zeg dat dan expliciet."
)

# Verplichte sleutels in elk Copilot-antwoord (§antwoord-schema)
ANSWER_KEYS = [
    "conclusion", "period", "sources", "data_freshness", "records",
    "confidence", "limitations", "warnings", "suggested_action", "links",
]

# Gesprekssamenvatting: bewaar de laatste N berichten ongecomprimeerd
SUMMARY_KEEP_RECENT = 6
# Geheugenextractie: elke N gebruikersvragen
MEMORY_EXTRACT_EVERY = 5
# Few-shot hergebruik: maximaal N voorbeelden per vraag
FEWSHOT_LIMIT = 3
# Geheugen: maximaal N geheugenitems per gebruiker+organisatie
MAX_MEMORY_ITEMS = 20

# Woordtokenizer voor Jaccard-similarity (few-shot matching)
_WORD_RE = re.compile(r"[a-záéíóúàèìòùäëïöüñç]{3,}", re.IGNORECASE)


# ─── Provider-configuratie (Task #79: expliciete providerkeuze) ─────────────
#
# Twee providers:
#   - PROVIDER_REPLIT ("replit_ai_openai"): Replit AI-integratie via
#     AI_INTEGRATIONS_OPENAI_BASE_URL / AI_INTEGRATIONS_OPENAI_API_KEY
#     (Replit-beheerde billing).
#   - PROVIDER_OPENAI ("openai_direct"): eigen OPENAI_API_KEY.
#
# De actieve provider is een beheerdersinstelling in de database
# (AiProviderSetting, singleton). Zonder expliciete keuze geldt de veilige
# standaard: Replit AI zodra die geconfigureerd is, anders de eigen sleutel.
# Een expliciete keuze valt NOOIT stil terug op de andere provider.

PROVIDER_REPLIT = "replit_ai_openai"
PROVIDER_OPENAI = "openai_direct"
KNOWN_PROVIDERS = (PROVIDER_REPLIT, PROVIDER_OPENAI)

PROVIDER_LABELS = {
    PROVIDER_REPLIT: "Replit AI (beheerde billing)",
    PROVIDER_OPENAI: "Eigen OpenAI-sleutel",
}

# Cache van de DB-instelling zodat _provider_config() geen DB-sessie nodig
# heeft op elk hot path (ai_available, _make_client). Korte TTL; wordt
# geïnvalideerd bij elke wissel via set_active_provider().
_SETTING_TTL_SECONDS = 30
_setting_cache: dict = {"value": None, "loaded": False, "checked_at": 0.0}


def _env_config(provider: str) -> Optional[dict]:
    """Env-configuratie voor één provider, of None als niet geconfigureerd."""
    if provider == PROVIDER_REPLIT:
        base = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        if base and key:
            return {"base_url": base, "api_key": key, "provider": PROVIDER_REPLIT}
        return None
    if provider == PROVIDER_OPENAI:
        direct = os.environ.get("OPENAI_API_KEY")
        if direct:
            return {"base_url": None, "api_key": direct, "provider": PROVIDER_OPENAI}
        return None
    return None


def provider_configured(provider: str) -> bool:
    return _env_config(provider) is not None


def _load_setting_from_db() -> Optional[str]:
    """Lees de persistente providerkeuze (None = automatisch)."""
    db = SessionLocal()
    try:
        row = db.query(models.AiProviderSetting).order_by(
            models.AiProviderSetting.id).first()
        return row.active_provider if row else None
    finally:
        db.close()


def get_chosen_provider() -> Optional[str]:
    """De expliciet gekozen provider uit de DB (gecachet), of None (auto)."""
    now = time.time()
    if _setting_cache["loaded"] and now - _setting_cache["checked_at"] < _SETTING_TTL_SECONDS:
        return _setting_cache["value"]
    try:
        value = _load_setting_from_db()
    except Exception as exc:
        # DB nog niet klaar (bv. tijdens opstarten): val terug op auto-modus,
        # maar cache dit niet als geldige waarde.
        logger.warning("Providerinstelling niet leesbaar: %s", exc)
        return _setting_cache["value"] if _setting_cache["loaded"] else None
    _setting_cache.update({"value": value, "loaded": True, "checked_at": now})
    return value


def set_active_provider(db, provider: Optional[str], updated_by: str) -> None:
    """Persisteer de providerkeuze (admin). provider=None → automatisch."""
    if provider is not None and provider not in KNOWN_PROVIDERS:
        raise ValueError(f"Onbekende provider: {provider}")
    row = db.query(models.AiProviderSetting).order_by(
        models.AiProviderSetting.id).first()
    if row is None:
        row = models.AiProviderSetting()
        db.add(row)
    row.active_provider = provider
    row.updated_by = updated_by
    row.updated_at = models.datetime.utcnow()
    db.commit()
    # Cache direct verversen + probes resetten zodat de wissel meteen geldt.
    _setting_cache.update({"value": provider, "loaded": True, "checked_at": time.time()})
    _probe_cache.clear()


def resolve_active_provider() -> Optional[str]:
    """Bepaal welke provider nu actief is.

    Expliciete keuze wint altijd (ook als die niet geconfigureerd is — dan is
    de AI-dienst bewust 'niet beschikbaar', geen stille terugval).
    Zonder keuze: Replit AI zodra geconfigureerd, anders eigen sleutel.
    """
    chosen = get_chosen_provider()
    if chosen is not None:
        return chosen
    if provider_configured(PROVIDER_REPLIT):
        return PROVIDER_REPLIT
    if provider_configured(PROVIDER_OPENAI):
        return PROVIDER_OPENAI
    return None


def _provider_config() -> Optional[dict]:
    """Configuratie van de actieve provider, of None als (de gekozen
    provider) niet geconfigureerd is. Geen stille terugval."""
    active = resolve_active_provider()
    if active is None:
        return None
    return _env_config(active)


def ai_available() -> bool:
    return _provider_config() is not None


# ─── Provider-bereikbaarheidstest (probe) ────────────────────────────────────
# Goedkope startup-/poll-check: roept models.list() aan (geen tokens verbruikt).
# Resultaat wordt per provider 5 minuten gecachet zodat herhaalde
# /api/copilot/status-calls de externe API niet spammen.

_PROBE_TTL_SECONDS = 300  # cache 5 minuten

# {provider: {"reachable": bool, "error": str|None, "checked_at": float}}
_probe_cache: dict = {}


def _probe_via_chat(client) -> tuple[bool, Optional[str]]:
    """Minimale chat-completion als bereikbaarheidstest voor providers
    waarvan de proxy GET /models niet ondersteunt. Verifieert de capaciteit
    die de Copilot daadwerkelijk gebruikt (auth + routering van completions)."""
    try:
        client.chat.completions.create(
            model=AI_MODEL,
            max_completion_tokens=16,
            messages=[{"role": "user", "content": "ping"}],
        )
        return True, None
    except Exception as exc:
        # Reasoning-modellen kunnen het lage tokenbudget overschrijden en
        # geven dan een 400 "output limit reached". De request is dan wél
        # geauthenticeerd en gerouteerd — provider is bereikbaar.
        msg = str(exc)
        if getattr(exc, "status_code", None) == 400 and "output limit" in msg.lower():
            return True, None
        return False, msg


def _run_probe(provider: str, timeout: float = 10.0) -> tuple[bool, Optional[str]]:
    """Voer een live bereikbaarheidstest uit voor één provider (geen cache)."""
    cfg = _env_config(provider)
    if cfg is None:
        return False, "Provider niet geconfigureerd (ontbrekende sleutel/omgeving)."
    try:
        from openai import OpenAI
        kwargs: dict = {"api_key": cfg["api_key"], "timeout": timeout}
        if cfg["base_url"]:
            kwargs["base_url"] = cfg["base_url"]
        client = OpenAI(**kwargs)
        client.models.list()
        return True, None
    except Exception as exc:
        # De Replit AI-gateway ondersteunt GET /models niet (404/405), terwijl
        # chat completions wél werken. Alleen voor die provider vallen we dan
        # terug op een minimale chat-completion om de daadwerkelijk gebruikte
        # capaciteit te verifiëren (resultaat wordt 5 min gecachet, dus de
        # kosten zijn begrensd). Voor openai_direct blijft 404/405 een fout.
        status_code = getattr(exc, "status_code", None)
        if provider == PROVIDER_REPLIT and status_code in (404, 405):
            return _probe_via_chat(client)
        error_msg = str(exc)
        logger.warning("AI provider-probe (%s) mislukt: %s", provider, error_msg)
        return False, error_msg


def probe_provider(force: bool = False, provider: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test of de (actieve) LLM-provider bereikbaar is.

    Gebruikt models.list() — geen tokenverbruik, geen kosten.
    Resultaat wordt _PROBE_TTL_SECONDS per provider gecachet.

    Returns (reachable, error_message).
    """
    target = provider or resolve_active_provider()
    if target is None:
        return False, "Geen AI-provider geconfigureerd."

    now = time.time()
    cached = _probe_cache.get(target)
    if not force and cached is not None and now - cached["checked_at"] < _PROBE_TTL_SECONDS:
        return cached["reachable"], cached["error"]

    reachable, error_msg = _run_probe(target)
    _probe_cache[target] = {"reachable": reachable, "error": error_msg, "checked_at": now}
    return reachable, error_msg


def get_provider_reachable() -> tuple[Optional[bool], Optional[str]]:
    """Geeft het gecachete probe-resultaat van de actieve provider terug
    zonder een nieuwe probe te starten.

    Returns (reachable_or_None, error_or_None).
    """
    target = resolve_active_provider()
    cached = _probe_cache.get(target) if target else None
    if cached is None:
        return None, None
    return cached["reachable"], cached["error"]


def provider_overview() -> dict:
    """Statusoverzicht voor het beheerderspaneel (Task #79)."""
    chosen = get_chosen_provider()
    active = resolve_active_provider()
    providers = []
    for pid in KNOWN_PROVIDERS:
        configured = provider_configured(pid)
        entry = {
            "id": pid,
            "label": PROVIDER_LABELS[pid],
            "configured": configured,
            "active": pid == active,
            "reachable": None,
            "error": None if configured else "Provider niet geconfigureerd (ontbrekende sleutel/omgeving).",
        }
        if pid == active and configured:
            reachable, error_msg = probe_provider(provider=pid)
            entry["reachable"] = reachable
            entry["error"] = error_msg
        providers.append(entry)
    return {
        "active_provider": active,
        "chosen_provider": chosen,   # None = automatisch
        "mode": "manual" if chosen is not None else "auto",
        "providers": providers,
    }


def _chat_completion_with_tools(client, **kwargs):
    """Chat-completion met function tools, compatibel met reasoning-modellen.

    Nieuwere modellen (o.a. gpt-5.6-terra) weigeren function tools op
    /v1/chat/completions zolang reasoning_effort actief is (400: "Function
    tools with reasoning_effort are not supported ... set reasoning_effort
    to 'none'"). Oudere modellen kennen reasoning_effort='none' juist niet.
    Daarom: eerst de standaard-aanroep; alleen bij díe specifieke 400 opnieuw
    proberen met reasoning_effort='none'. Geen stille terugval op een ander
    model — alleen deze parameter wordt aangepast."""
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        msg = str(exc)
        if getattr(exc, "status_code", None) == 400 and "reasoning_effort" in msg:
            logger.info("Model %s vereist reasoning_effort='none' bij tools; "
                        "opnieuw geprobeerd.", kwargs.get("model"))
            return client.chat.completions.create(reasoning_effort="none", **kwargs)
        raise


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
# (?<!\d): start nooit midden in een cijferreeks — voorkomt dat ISO-datetimes
# zoals "2026-08-19 02:59:17" gedeeltelijk als telefoonnummer worden gemaskeerd.
# (?!\d): eindig niet midden in een langere cijferreeks (geen telefoonnummer).
_PHONE_RE = re.compile(r"(?<!\d)(\+31|0031|0)[\s-]?\d[\s-]?(\d[\s-]?){7,9}(?!\d)")
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


# ─── Dagelijks budgetbewaking (§34) ─────────────────────────────────────────

DEFAULT_MAX_CALLS_PER_DAY = int(os.environ.get("AI_MAX_CALLS_PER_DAY", "50"))
DEFAULT_MAX_TOKENS_PER_DAY = int(os.environ.get("AI_MAX_TOKENS_PER_DAY", "500000"))

# Worst-case tokenreservering per aanvraag, upfront vergrendeld vóór de eerste
# LLM-aanroep. Dekt alle MAX_TOOL_ROUNDS rondes inclusief invoertokens:
#   - Voltooiingstokens: MAX_TOOL_ROUNDS × max_completion_tokens (8192) = 49.152
#   - Invoertokens (systeem-prompt, geschiedenis, toolresultaten): vergelijkbaar
# Totale reservering = MAX_TOOL_ROUNDS × 8192 × 2 ≈ 98.304 tokens.
# reconcile_budget_slot() geeft het ongebruikte deel terug na de call.
_MAX_COMPLETION_PER_CALL = 8192                                      # max_completion_tokens
_UPFRONT_TOKEN_RESERVATION = MAX_TOOL_ROUNDS * _MAX_COMPLETION_PER_CALL * 2  # ≈ 98_304

# Kleinere reservering voor interne hulp-calls (samenvatting, geheugenextractie):
# max_completion_tokens=1024, transcript ≤ 20 000 chars ≈ 5 000 tokens invoer.
# Worst case ≈ 6 024; we reserveren één rondebudget (8 192) als veiligheidsmarge.
_UPFRONT_AUXILIARY_RESERVATION = _MAX_COMPLETION_PER_CALL  # 8_192

def _get_budget_config(db: Session, username: str) -> tuple[Optional[int], Optional[int]]:
    """Haal de effectieve limiet op: gebruikersspecifiek → globaal → env-standaard."""
    user_row = db.query(models.AiBudgetConfig).filter(
        models.AiBudgetConfig.username == username
    ).first()
    if user_row:
        return user_row.max_calls_per_day, user_row.max_tokens_per_day

    global_row = db.query(models.AiBudgetConfig).filter(
        models.AiBudgetConfig.username.is_(None)
    ).first()
    if global_row:
        return global_row.max_calls_per_day, global_row.max_tokens_per_day

    return DEFAULT_MAX_CALLS_PER_DAY, DEFAULT_MAX_TOKENS_PER_DAY

def _log_budget_exceeded(username: str, user_role: str, reason: str) -> None:
    """Log een budgetoverschrijding in een aparte kortstondige sessie."""
    log_db = SessionLocal()
    try:
        log_db.add(models.AiModelCall(
            username=username, user_role=user_role,
            purpose="copilot_question", provider="none",
            model=AI_MODEL, prompt_tokens=0, completion_tokens=0,
            total_tokens=0, llm_roundtrips=0, duration_ms=0,
            status="budget_exceeded", error_message=reason,
        ))
        log_db.commit()
    except Exception as exc:
        logger.warning("Logging budget_exceeded mislukt: %s", exc)
        log_db.rollback()
    finally:
        log_db.close()
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
    slot_date: Optional[date] = None,
    max_tokens: Optional[int] = None,
    budget_warning: Optional[str] = None,
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

    # _log_call zit in een finally-blok zodat het ook bij vroegtijdige sluiting
    # van de generator (client-disconnect, generator.close()) altijd wordt
    # aangeroepen — en daarmee ook reconcile_budget_slot (§34). Het is
    # gegarandeerd exactly-once: de return in het no-provider-pad bereikt
    # alsnog de finally voordat de generator stopt.
    try:
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
            error_message = "AI-provider niet geconfigureerd"
            return  # finally loopt alsnog na return in een generator

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
                # Pre-ronde schatting (§34): controleer vóór de LLM-aanroep of de
                # berichten nog binnen de per-verzoek tokenruimte passen. Dit voorkomt
                # dat grote tool-outputs de reservering overschrijden door ook de
                # invoertokens mee te tellen vóór de call in plaats van alleen erna.
                if max_tokens is not None:
                    est_prompt = len(json.dumps(messages, default=str)) // 4
                    if (usage["total_tokens"] + est_prompt + _MAX_COMPLETION_PER_CALL
                            > _UPFRONT_TOKEN_RESERVATION):
                        answer = _default_answer(
                            "De beschikbare tokenruimte voor dit verzoek is bijna op. "
                            "Stel een kortere of specifiekere vraag om binnen het "
                            "dagbudget te blijven.",
                            [f"Geschatte prompt ({est_prompt:,} tokens) + "
                             f"voltooiing ({_MAX_COMPLETION_PER_CALL:,}) zou de "
                             f"reservering ({_UPFRONT_TOKEN_RESERVATION:,} tokens) "
                             "overschrijden."],
                            freshness,
                        )
                        status = "budget_exceeded"
                        break

                resp = _chat_completion_with_tools(
                    client,
                    model=AI_MODEL,
                    max_completion_tokens=_MAX_COMPLETION_PER_CALL,
                    messages=messages,
                    tools=tools,
                )
                roundtrips += 1
                if resp.usage:
                    usage["prompt_tokens"] += resp.usage.prompt_tokens or 0
                    usage["completion_tokens"] += resp.usage.completion_tokens or 0
                    usage["total_tokens"] += resp.usage.total_tokens or 0

                # Post-ronde tokencontrole (§34): stop verdere rondes zodra dit
                # verzoek zijn upfront-reservering heeft opgebruikt. Door te
                # vergelijken met _UPFRONT_TOKEN_RESERVATION (de per-verzoek
                # toewijzing) in plaats van max_tokens (de dagelijkse limiet)
                # wordt ook het eerder door andere verzoeken verbruikte dagbudget
                # correct meegewogen: de toewijzing is immer gelijk aan de
                # reservering, ongeacht hoeveel tokens eerder die dag zijn gebruikt.
                if max_tokens is not None and usage["total_tokens"] >= _UPFRONT_TOKEN_RESERVATION:
                    answer = _default_answer(
                        "De tokenruimte voor dit verzoek is bereikt. Stel een kortere of "
                        "specifiekere vraag, of neem contact op met een beheerder voor een "
                        "hogere dagelijkse limiet.",
                        [f"Verzoek-tokenlimiet bereikt "
                         f"({usage['total_tokens']:,} ≥ {_UPFRONT_TOKEN_RESERVATION:,} tokens)."],
                        freshness,
                    )
                    status = "budget_exceeded"
                    break

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
        # Vroegtijdige budgetwaarschuwing (Task #53): ≥ 80% dagverbruik
        if budget_warning and budget_warning not in answer["warnings"]:
            answer["warnings"].append(budget_warning)
        for k in ANSWER_KEYS:
            answer.setdefault(k, None)

        # Belt-and-braces: ook het eindantwoord zelf wordt gescrubd vóór
        # weergave en persistentie (het model kan PII uit de vraag echoën).
        answer = pii_scrub(answer)

        yield {"type": "answer", "answer": answer}

    finally:
        # Gegarandeerd aangeroepen: normaal einde, vroegtijdig sluiten (disconnect),
        # en het no-provider return-pad. reconcile_budget_slot loopt hier altijd.
        # slot_date wordt doorgegeven zodat reconciliatie de juiste dag bijwerkt.
        _log_call(db, user, conversation_id, purpose, provider or "none", calls_meta,
                  usage, roundtrips, started, status, error_message,
                  prompt_version_id=prompt_version_id, slot_date=slot_date)


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


def _log_call(
    db: Session,
    user: models.User,
    conversation_id: Optional[int],
    purpose: str,
    provider: str,
    calls_meta: list[dict],
    usage: dict,
    roundtrips: int,
    started: float,
    status: str,
    error_message: Optional[str],
    prompt_version_id: Optional[int] = None,
    slot_date: Optional[date] = None,
    reserved_tokens: int = _UPFRONT_TOKEN_RESERVATION,
) -> None:
    """Log de gateway-call in AiModelCall + CostUsageRecord. Faalt stil-veilig.

    reserved_tokens moet overeenkomen met het bedrag dat bij reservering is
    geboekt. Primaire calls gebruiken _UPFRONT_TOKEN_RESERVATION; hulp-calls
    (samenvatting, geheugen) geven _UPFRONT_AUXILIARY_RESERVATION mee."""
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
        # Reconcilieer het slot-budget met het werkelijke tokenverbruik (§34).
        # slot_date wordt doorgegeven zodat een call die net na middernacht eindigt
        # de reservering van de juiste dag bijwerkt.
        # Alleen reconciliëren als er een reservering is gemaakt (slot_date is None
        # voor interne calls zonder slot, maar hulp-calls geven altijd hun slot_date mee).
        if slot_date is not None:
            reconcile_budget_slot(db, user.username, usage["total_tokens"],
                                  slot_date=slot_date,
                                  reserved_tokens=reserved_tokens)
        db.commit()
    except Exception as exc:
        logger.warning("AI Gateway-logging mislukt: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass

# Drempel waarboven een vroegtijdige budgetwaarschuwing wordt gegeven (§34):
# bij ≥ 80% verbruik van calls of tokens krijgt de gebruiker een melding in
# answer.warnings, zodat de harde 429-blokkade niet als verrassing komt.
BUDGET_WARNING_THRESHOLD = 0.80


def _budget_usage_warning(
    calls_used: int, max_calls: Optional[int],
    tokens_used: int, max_tokens: Optional[int],
) -> Optional[str]:
    """Bouw een waarschuwingstekst als het verbruik ≥ 80% van een daglimiet is.

    calls_used/tokens_used zijn de tellers ná reservering van de huidige call,
    zodat de melding het actuele verbruik weerspiegelt. Geen limiet (None of 0)
    → nooit een waarschuwing voor die dimensie.
    """
    parts: list[str] = []
    if max_calls and calls_used / max_calls >= BUDGET_WARNING_THRESHOLD:
        pct = min(100, int(calls_used / max_calls * 100))
        parts.append(f"{pct}% van je dagelijkse AI-call-limiet "
                     f"({calls_used}/{max_calls} calls)")
    if max_tokens and tokens_used / max_tokens >= BUDGET_WARNING_THRESHOLD:
        pct = min(100, int(tokens_used / max_tokens * 100))
        parts.append(f"{pct}% van je dagelijkse tokenlimiet "
                     f"({tokens_used:,}/{max_tokens:,} tokens gereserveerd)")
    if not parts:
        return None
    return ("Let op: je hebt " + " en ".join(parts) + " verbruikt. "
            "Bij het bereiken van de limiet worden nieuwe vragen vandaag "
            "geblokkeerd; stel vragen gerichter of neem contact op met een "
            "beheerder voor een hogere limiet.")


def check_and_reserve_budget(
    username: str, user_role: str
) -> tuple[date, Optional[int], Optional[str]]:
    """
    Atomisch budgetbewaking vóór elke LLM-call (§34).

    Opent een eigen kortstondige sessie (onafhankelijk van de request-sessie)
    en gebruikt SELECT FOR UPDATE zodat parallelle verzoeken nooit tegelijk
    doorheen glippen. Reserveert _UPFRONT_TOKEN_RESERVATION tokens per call
    zodat het dagbudget ook niet overschreden kan worden door één grote call
    die pas achteraf wordt geteld.

    Gooit HTTPException 429 met een Nederlandse foutmelding bij overschrijding.
    Geeft (slot_date, max_tokens, budget_warning) terug zodat de beller dezelfde
    datum en limiet kan doorgeven aan run_copilot (correcte reconciliatie bij
    middernacht), per-ronde token-controles kan uitvoeren, en een vroegtijdige
    waarschuwing (≥ 80% dagverbruik) in het antwoord kan tonen.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    today = date.today()
    db = SessionLocal()
    try:
        # 1. Haal limieten op (niet-lockend; config wijzigt zelden)
        max_calls, max_tokens = _get_budget_config(db, username)

        # 2. Zorg dat de slot-rij voor vandaag bestaat (INSERT OR IGNORE)
        db.execute(
            pg_insert(models.AiBudgetSlot).values(
                username=username, slot_date=today,
                calls_reserved=0, tokens_reserved=0, tokens_actual=0,
            ).on_conflict_do_nothing()
        )
        db.flush()

        # 3. Lock de slot-rij zodat gelijktijdige verzoeken serialiseren
        slot = db.query(models.AiBudgetSlot).filter(
            models.AiBudgetSlot.username == username,
            models.AiBudgetSlot.slot_date == today,
        ).with_for_update().one()

        # 4. Controleer limieten en reserveer atomisch
        exceeded_reason: Optional[str] = None
        if max_calls is not None and slot.calls_reserved >= max_calls:
            exceeded_reason = (
                f"dagelijkse call-limiet bereikt ({slot.calls_reserved}/{max_calls} calls)"
            )
        elif max_tokens is not None and (
            slot.tokens_reserved + _UPFRONT_TOKEN_RESERVATION > max_tokens
        ):
            exceeded_reason = (
                f"dagelijkse token-limiet bereikt ("
                f"{slot.tokens_reserved:,} gereserveerd "
                f"+ {_UPFRONT_TOKEN_RESERVATION:,} nodig "
                f"> {max_tokens:,} limiet)"
            )

        if exceeded_reason:
            db.rollback()
            logger.warning(
                "AI-budgetlimiet overschreden voor gebruiker '%s': %s",
                username, exceeded_reason,
            )
            _log_budget_exceeded(username, user_role, exceeded_reason)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Je hebt je dagelijkse AI-limiet bereikt ({exceeded_reason}). "
                    "Je kunt morgen weer vragen stellen. Neem contact op met een beheerder "
                    "als je een hogere limiet nodig hebt."
                ),
            )

        # 5. Reserveer atomisch (binnen de FOR UPDATE lock)
        slot.calls_reserved += 1
        slot.tokens_reserved += _UPFRONT_TOKEN_RESERVATION
        db.commit()

        # 6. Vroegtijdige waarschuwing (Task #53): meld ≥ 80% dagverbruik zodat
        # de gebruiker niet verrast wordt door de harde blokkade op 100%.
        budget_warning = _budget_usage_warning(
            slot.calls_reserved, max_calls,
            slot.tokens_reserved, max_tokens,
        )
        return today, max_tokens, budget_warning

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("check_and_reserve_budget fout: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()


def _try_reserve_auxiliary_budget(username: str, user_role: str) -> Optional[date]:
    """
    Fail-safe budgetreservering voor interne hulp-calls (samenvatting,
    geheugenextractie). Reserveert _UPFRONT_AUXILIARY_RESERVATION tokens.

    Geeft de slot_date terug als er ruimte is, of None als het budget op is
    (dan wordt de hulp-call overgeslagen). Gooit nooit een HTTPException.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    today = date.today()
    db = SessionLocal()
    try:
        max_calls, max_tokens = _get_budget_config(db, username)

        db.execute(
            pg_insert(models.AiBudgetSlot).values(
                username=username, slot_date=today,
                calls_reserved=0, tokens_reserved=0, tokens_actual=0,
            ).on_conflict_do_nothing()
        )
        db.flush()

        slot = db.query(models.AiBudgetSlot).filter(
            models.AiBudgetSlot.username == username,
            models.AiBudgetSlot.slot_date == today,
        ).with_for_update().one()

        if max_calls is not None and slot.calls_reserved >= max_calls:
            logger.info(
                "Hulp-call overgeslagen voor '%s': call-limiet bereikt (%d/%d)",
                username, slot.calls_reserved, max_calls,
            )
            db.rollback()
            return None
        if max_tokens is not None and (
            slot.tokens_reserved + _UPFRONT_AUXILIARY_RESERVATION > max_tokens
        ):
            logger.info(
                "Hulp-call overgeslagen voor '%s': token-limiet bereikt (%d + %d > %d)",
                username, slot.tokens_reserved, _UPFRONT_AUXILIARY_RESERVATION, max_tokens,
            )
            db.rollback()
            return None

        slot.calls_reserved += 1
        slot.tokens_reserved += _UPFRONT_AUXILIARY_RESERVATION
        db.commit()
        return today

    except Exception as exc:
        logger.warning("_try_reserve_auxiliary_budget fout: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


def maybe_summarize_conversation(db: Session, user: models.User,
                                 conversation_id: int) -> None:
    """Vat oudere berichten van een lang gesprek samen (i.p.v. afkappen).
    Fail-safe: fouten worden gelogd, nooit doorgegeven.
    Controleer en reserveer budget vóór de LLM-call (§34)."""
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
        # Budgetcontrole vóór de LLM-aanroep (fail-safe: overslaan bij overschrijding)
        aux_slot_date = _try_reserve_auxiliary_budget(user.username, user.role)
        if aux_slot_date is None:
            logger.info("Gesprekssamenvatting overgeslagen: budgetlimiet bereikt voor '%s'",
                        user.username)
            return
        # try/finally garandeert altijd reconciliatie — ook als _make_client None geeft
        # of de LLM-aanroep mislukt — zodat de gereserveerde tokens vrijkomen.
        started = time.time()
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        provider = "none"
        status = "error"
        error_msg: Optional[str] = None
        try:
            client, provider = _make_client()
            if client is None:
                return  # finally-blok zorgt voor reconciliatie
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
            usage = {"prompt_tokens": (resp.usage.prompt_tokens or 0) if resp.usage else 0,
                     "completion_tokens": (resp.usage.completion_tokens or 0) if resp.usage else 0,
                     "total_tokens": (resp.usage.total_tokens or 0) if resp.usage else 0}
            if summary:
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
            status = "success"
        except Exception as exc:
            error_msg = str(exc)
            raise
        finally:
            _log_call(db, user, conversation_id, "conversation_summary", provider,
                      [], usage, 1, started, status, error_msg,
                      slot_date=aux_slot_date,
                      reserved_tokens=_UPFRONT_AUXILIARY_RESERVATION)
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
    Fail-safe: fouten worden gelogd, nooit doorgegeven.
    Controleer en reserveer budget vóór de LLM-call (§34)."""
    try:
        user_msgs = (db.query(models.AiMessage)
                     .filter(models.AiMessage.conversation_id == conversation_id,
                             models.AiMessage.role == "user")
                     .order_by(models.AiMessage.id).all())
        if not user_msgs or len(user_msgs) % MEMORY_EXTRACT_EVERY != 0:
            return
        # Budgetcontrole vóór de LLM-aanroep (fail-safe: overslaan bij overschrijding)
        aux_slot_date = _try_reserve_auxiliary_budget(user.username, user.role)
        if aux_slot_date is None:
            logger.info("Geheugenextractie overgeslagen: budgetlimiet bereikt voor '%s'",
                        user.username)
            return
        # try/finally garandeert altijd reconciliatie — ook als _make_client None geeft
        # of de LLM-aanroep mislukt — zodat de gereserveerde tokens vrijkomen.
        started = time.time()
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        provider = "none"
        status = "error"
        error_msg: Optional[str] = None
        try:
            client, provider = _make_client()
            if client is None:
                return  # finally-blok zorgt voor reconciliatie
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
            usage = {"prompt_tokens": (resp.usage.prompt_tokens or 0) if resp.usage else 0,
                     "completion_tokens": (resp.usage.completion_tokens or 0) if resp.usage else 0,
                     "total_tokens": (resp.usage.total_tokens or 0) if resp.usage else 0}
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
                    # Tombstone: door de gebruiker verwijderde keys mogen
                    # nooit stilletjes terugkeren via extractie (Task #135).
                    if (row.status or "active") == "deleted":
                        continue
                    # Handmatig gecorrigeerde waarden winnen van extractie.
                    if (row.source or "extracted") == "manual":
                        continue
                    row.value = value
                    row.source_conversation_id = conversation_id
                    row.updated_at = datetime.utcnow()
                else:
                    db.add(models.AiUserMemory(
                        user_id=user.id, key=key, value=value,
                        source_conversation_id=conversation_id))
            db.commit()
            status = "success"
        except Exception as exc:
            error_msg = str(exc)
            raise
        finally:
            _log_call(db, user, conversation_id, "memory_extraction", provider,
                      [], usage, 1, started, status, error_msg,
                      slot_date=aux_slot_date,
                      reserved_tokens=_UPFRONT_AUXILIARY_RESERVATION)
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
                        (models.AiUserMemory.user_id.is_(None)),
                        models.AiUserMemory.status == "active")
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

def _dedupe_examples(scored_rows, limit: int) -> list[dict]:
    """Ontdubbel op vraagtekst en knip af op `limit`.

    `scored_rows` is een lijst (score, AiFeedback), al gesorteerd op
    relevantie (hoogste eerst)."""
    seen: set[str] = set()
    out: list[dict] = []
    for _score, r in scored_rows:
        key = (r.question or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"question": r.question, "answer": r.answer_excerpt})
        if len(out) >= limit:
            break
    return out
def get_fewshot_examples(db: Session, question: str,
                         limit: int = FEWSHOT_LIMIT) -> list[dict]:
    """Zoek eerder positief beoordeelde, vergelijkbare vragen+antwoorden.

    Primair via Postgres full-text search met Nederlandse stemmer (vindt ook
    anders geformuleerde vragen); fail-safe terugval op woordoverlap als de
    zoekindex/FTS niet beschikbaar is."""
    try:
        return _fewshot_rows_fts(db, question, limit)
    except Exception as exc:
        logger.warning("Few-shot FTS niet beschikbaar, terugval op woordoverlap: %s", exc)
        try:
            db.rollback()  # mislukte FTS-query laat de transactie aborted achter
        except Exception:
            pass
    try:
        return _fewshot_rows_overlap(db, question, limit)
    except Exception:
        return []

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


def reconcile_budget_slot(
    db: Session,
    username: str,
    actual_tokens: int,
    slot_date: Optional[date] = None,
    reserved_tokens: int = _UPFRONT_TOKEN_RESERVATION,
) -> None:
    """
    Werk tokens_actual bij en corrigeer de reservering (§34).

    slot_date MOET de datum zijn die check_and_reserve_budget (of
    _try_reserve_auxiliary_budget) heeft teruggegeven; anders werkt een call
    die rond middernacht eindigt de reservering van de vorige dag bij.
    Valt terug op date.today() als slot_date None is (backward-compat).

    reserved_tokens MOET overeenkomen met het bedrag dat bij reservering is
    geboekt (_UPFRONT_TOKEN_RESERVATION voor primaire calls,
    _UPFRONT_AUXILIARY_RESERVATION voor hulp-calls). Hiermee berekent:

    net_change = actual - reserved:
      < 0 → release ongebruikte tokens
      > 0 → boek overrun, zodat volgende calls de echte resterende ruimte zien
    """
    try:
        effective_date = slot_date if slot_date is not None else date.today()
        db.query(models.AiBudgetSlot).filter(
            models.AiBudgetSlot.username == username,
            models.AiBudgetSlot.slot_date == effective_date,
        ).update(
            {
                models.AiBudgetSlot.tokens_actual:
                    models.AiBudgetSlot.tokens_actual + actual_tokens,
                # net_change < 0 → release | net_change > 0 → charge overrun
                models.AiBudgetSlot.tokens_reserved:
                    func.greatest(
                        0,
                        models.AiBudgetSlot.tokens_reserved
                        + (actual_tokens - reserved_tokens),
                    ),
            },
            synchronize_session=False,
        )
    except Exception as exc:
        logger.warning("reconcile_budget_slot mislukt: %s", exc)

def release_budget_slot_reservation(
    db: Session, username: str, slot_date: date
) -> None:
    """
    Geef een slot-reservering volledig terug als de LLM-call nooit is gestart (§34).

    Wordt aangeroepen als:
    - het opslaan van het gebruikersbericht faalt na reservering, of
    - de SSE-generator nooit geïtereerd is (client-disconnect vóór eerste byte).
    """
    try:
        db.query(models.AiBudgetSlot).filter(
            models.AiBudgetSlot.username == username,
            models.AiBudgetSlot.slot_date == slot_date,
        ).update(
            {
                models.AiBudgetSlot.calls_reserved:
                    func.greatest(0, models.AiBudgetSlot.calls_reserved - 1),
                models.AiBudgetSlot.tokens_reserved:
                    func.greatest(
                        0,
                        models.AiBudgetSlot.tokens_reserved - _UPFRONT_TOKEN_RESERVATION,
                    ),
            },
            synchronize_session=False,
        )
        db.commit()
    except Exception as exc:
        logger.warning("release_budget_slot_reservation mislukt: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass

def _fewshot_rows_overlap(db: Session, question: str, limit: int) -> list[dict]:
    """Fallback-retrieval: Jaccard-woordoverlap over recente positieve
    feedback (het oorspronkelijke gedrag). Fail-safe als FTS niet werkt."""
    rows = (db.query(models.AiFeedback)
            .filter(models.AiFeedback.score > 0,
                    models.AiFeedback.question.isnot(None),
                    models.AiFeedback.answer_excerpt.isnot(None))
            .order_by(models.AiFeedback.created_at.desc())
            .limit(200).all())
    scored = []
    for r in rows:
        sim = _similarity(question, r.question or "")
        if sim >= 0.25:
            scored.append((sim, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    return _dedupe_examples(scored, limit)

def _fewshot_rows_fts(db: Session, question: str, limit: int) -> list[dict]:
    """Primaire retrieval: Postgres full-text search met Nederlandse stemmer.

    Vindt vergelijkbare vragen ook zonder letterlijke woordoverlap: de
    'dutch'-configuratie stemt vervoegingen (verliezen → verlies) en negeert
    stopwoorden ("waar", "we"), en de query gebruikt OR-semantiek over de
    lexemen zodat gedeeltelijke overlap volstaat. Gooit een exception door
    als FTS niet beschikbaar is (caller valt dan terug op woordoverlap)."""
    words = _WORD_RE.findall(question.lower())
    if not words:
        return []
    # OR-tsquery over de losse woorden; _WORD_RE laat alleen letters door,
    # dus de lexemen zijn veilig om te concateneren.
    tsquery = func.to_tsquery("dutch", " | ".join(dict.fromkeys(words)))
    tsvector = func.to_tsvector("dutch", models.AiFeedback.question)
    rank = func.ts_rank(tsvector, tsquery)
    rows = (db.query(models.AiFeedback, rank.label("rank"))
            .filter(models.AiFeedback.score > 0,
                    models.AiFeedback.question.isnot(None),
                    models.AiFeedback.answer_excerpt.isnot(None),
                    tsvector.op("@@")(tsquery))
            .order_by(rank.desc(), models.AiFeedback.created_at.desc())
            .limit(50).all())
    scored = [(float(r.rank), r[0]) for r in rows if float(r.rank) >= FTS_MIN_RANK]
    return _dedupe_examples(scored, limit)
