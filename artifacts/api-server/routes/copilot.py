"""
Commercial AI Copilot routes (§26) — /api/copilot/...

Chat met gespreksgeschiedenis; elk antwoord loopt via de AI Gateway
(ai_gateway.py) en is dus beperkt tot approved semantic-layer-functies.
"""
import json
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

import ai_gateway
import auth as auth_utils
import authz
import models
from database import get_db
from services import product_scope as product_scope_service

router = APIRouter(prefix="/api/copilot", tags=["copilot"])

# Gecureerde, versiebeheerbare gespreksstarters. Een starter is een template,
# geen gesprek: pas na een klik wordt een gebruiker-eigen conversatie gemaakt.
COPILOT_STARTERS = [
    {"key": "competitors-attention", "module_key": "competition", "module_label": "Concurrentie",
     "title": "Belangrijkste concurrenten", "question": "Welke concurrenten zijn binnen mijn huidige selectie het belangrijkst en waarom?",
     "description": "Rangschikt concurrenten op invloed en licht de belangrijkste factoren toe.", "required_function": "get_competitor_ranking"},
    {"key": "position-one-room", "module_key": "competition", "module_label": "Concurrentie",
     "title": "Positie 1 en prijsruimte", "question": "Waar staan wij op positie 1 en waar kunnen we veilig verhogen?",
     "description": "Zoekt producten waar de eigen prijs marktleider is en duidt prijsruimte.", "required_function": "get_portfolio_price_position"},
    {"key": "more-expensive", "module_key": "competition", "module_label": "Concurrentie",
     "title": "Duurder dan de markt", "question": "Bij welke producten zijn wij duurder dan onze belangrijkste concurrenten?",
     "description": "Brengt ongunstige prijsposities binnen de actieve selectie in beeld.", "required_function": "get_portfolio_price_position"},
    {"key": "price-winner", "module_key": "competition", "module_label": "Concurrentie",
     "title": "Wie wint op prijs?", "question": "Welke concurrent wint het vaakst op prijs binnen deze categorie?",
     "description": "Vergelijkt de prijspositie van aanbieders binnen de huidige categorie.", "required_function": "get_competitor_ranking"},
    {"key": "excluded-prices", "module_key": "competition", "module_label": "Concurrentie",
     "title": "Uitgesloten prijzen", "question": "Welke uitgesloten concurrentprijzen beïnvloeden de vergelijking niet?",
     "description": "Legt uit welke observaties buiten de betrouwbare vergelijking vallen.", "required_function": "get_price_position"},
    {"key": "margin-loss", "module_key": "pricing", "module_label": "Pricing & aanbevelingen",
     "title": "Margeverlies vinden", "question": "Waar verliezen we op dit moment marge?",
     "description": "Toont de grootste margedalingen en waar actie nodig is.", "required_function": "get_margin_erosion"},
    {"key": "price-simulation", "module_key": "pricing", "module_label": "Pricing & aanbevelingen",
     "title": "Prijswijziging simuleren", "question": "Wat gebeurt er met omzet en marge als ik het geselecteerde product 3% duurder maak?",
     "description": "Berekent de verwachte impact van een prijswijziging.", "required_function": "simulate_price_change"},
    {"key": "private-label", "module_key": "assortment", "module_label": "Assortiment & substitutie",
     "title": "Huismerkpotentie", "question": "Welke producten hebben de grootste huismerkpotentie?",
     "description": "Vindt producten met kansrijke huismerkalternatieven.", "required_function": "get_private_label_potential"},
    {"key": "switching", "module_key": "assortment", "module_label": "Assortiment & substitutie",
     "title": "Overstap naar huismerk", "question": "Hoeveel switching-volume zien we van A-merk naar huismerk?",
     "description": "Analyseert interne overstapbewegingen tussen merktypen.", "required_function": "get_customer_switching"},
    {"key": "break-even", "module_key": "sales", "module_label": "Verkoop, marge & break-even",
     "title": "Omzet en marge", "question": "Hoe ontwikkelen omzet, afzet en marge zich binnen mijn huidige selectie?",
     "description": "Vat commerciële prestaties voor de actieve scope samen.", "required_function": "get_category_performance"},
    {"key": "promotion", "module_key": "sales", "module_label": "Verkoop, marge & break-even",
     "title": "Effectieve promoties", "question": "Welke promotie werkte het afgelopen kwartaal het best?",
     "description": "Vergelijkt gemeten uplift en incrementele marge.", "required_function": "get_promotion_effectiveness"},
    {"key": "supplier-risk", "module_key": "forecast", "module_label": "Voorraad, forecast & inkoop",
     "title": "Leveranciersrisico", "question": "Bij welke leveranciers lopen we margerisico?",
     "description": "Brengt inkooprisico en margedruk per leverancier of product in beeld.", "required_function": "get_supplier_risk"},
    {"key": "active-signals", "module_key": "data_quality", "module_label": "Data quality & imports",
     "title": "Dataproblemen met impact", "question": "Welke actieve signalen vragen nu aandacht en op welke data zijn ze gebaseerd?",
     "description": "Vat actuele signalen en hun brondata samen.", "required_function": "get_active_signals"},
    {"key": "opportunities", "module_key": "management", "module_label": "Management & kansen",
     "title": "Grootste kansen", "question": "Wat zijn nu onze grootste commerciële kansen?",
     "description": "Rangschikt kansen uit de centrale Opportunity Engine.", "required_function": "get_opportunities"},
    {"key": "traffic", "module_key": "management", "module_label": "Management & kansen",
     "title": "Traffic en conversie", "question": "Hoe ontwikkelen traffic en conversie zich?",
     "description": "Geeft een managementsamenvatting van bereik en conversie.", "required_function": "get_traffic_summary"},
]

STARTERS_BY_KEY = {s["key"]: s for s in COPILOT_STARTERS}
MODULE_LABELS = {s["module_key"]: s["module_label"] for s in COPILOT_STARTERS}
EXAMPLE_QUESTIONS = [s["question"] for s in COPILOT_STARTERS if s["module_key"] == "competition"]


def _starter_library(db: Session, user: models.User) -> list[dict]:
    allowed = ai_gateway.allowed_function_names(db, user)
    result = []
    for starter in COPILOT_STARTERS:
        available = starter["required_function"] in allowed
        result.append({
            **starter,
            "available": available,
            "availability_reason": None if available else
                "Niet beschikbaar voor jouw rol of afdeling.",
        })
    return result


def _conversation_out(c: models.AiConversation) -> dict:
    return {
        "id": c.id,
        "shop_id": c.shop_id,
        "title": c.title,
        "module_key": c.module_key or "general",
        "module_label": MODULE_LABELS.get(c.module_key or "general", "Algemeen"),
        "starter_key": c.starter_key,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _message_out(m: models.AiMessage) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "answer": m.answer_json,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _own_conversation(
    db: Session, user: models.User, conversation_id: int,
    requested_shop_id: Optional[int] = None,
) -> models.AiConversation:
    conv = db.query(models.AiConversation).filter(
        models.AiConversation.id == conversation_id,
        models.AiConversation.user_id == user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Gesprek niet gevonden")
    allowed_shops = authz.user_allowed_shop_ids(db, user)
    if allowed_shops is not None and conv.shop_id not in allowed_shops:
        # Gebruik 404 zodat geen gesprek-id of voormalige toegang wordt gelekt.
        raise HTTPException(status_code=404, detail="Gesprek niet gevonden")
    if requested_shop_id is not None and conv.shop_id != requested_shop_id:
        raise HTTPException(status_code=404, detail="Gesprek niet gevonden")
    return conv


@router.get("/status")
def copilot_status(
    current_user: models.User = Depends(auth_utils.get_current_user),
    db: Session = Depends(get_db),
):
    """Beschikbaarheid van de AI-dienst + voorbeeldvragen (§26).

    `provider_reachable` geeft aan of de externe API-sleutel geldig en bereikbaar
    is (gecachet; vernieuwd bij opstarten en daarna elke 5 minuten op verzoek).
    `provider_error` bevat de foutmelding als de probe mislukt is.
    """
    # probe_provider() is TTL-bewust (5 minuten cache): het voert alleen een
    # nieuwe netwerkoproep uit als de cache verlopen is. Zo is de status-response
    # altijd vers zonder de externe API te spammen.
    reachable, probe_error = ai_gateway.probe_provider()
    return {
        "ai_available": ai_gateway.ai_available(),
        "provider_reachable": reachable,
        "provider_error": probe_error,
        "model": ai_gateway.AI_MODEL,
        "example_questions": EXAMPLE_QUESTIONS,
        "starter_library": _starter_library(db, current_user),
        # Alleen functies die deze gebruiker vanuit zijn afdelingsrechten mag
        # gebruiken (taak 220) — zelfde allowlist als het toolaanbod in de
        # gateway.
        "approved_functions": [
            {"name": name, "description": f.description}
            for name, f in ai_gateway.SEMANTIC_FUNCTIONS.items()
            if name in ai_gateway.allowed_function_names(db, current_user)
        ],
        "data_freshness": ai_gateway.get_data_freshness(db),
    }


@router.get("/conversations")
def list_conversations(
    shop_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    from semantic_layer import _shop_scope
    sid = _shop_scope(db, shop_id)
    allowed_shops = authz.user_allowed_shop_ids(db, current_user)
    if allowed_shops is not None and sid not in allowed_shops:
        raise HTTPException(status_code=403, detail="Geen toegang tot deze winkel")
    rows = db.query(models.AiConversation).filter(
        models.AiConversation.user_id == current_user.id,
        models.AiConversation.shop_id == sid,
    ).order_by(desc(models.AiConversation.updated_at)).limit(100).all()
    return [_conversation_out(c) for c in rows]


@router.post("/conversations")
def create_conversation(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    starter_key = (payload.get("starter_key") or "").strip() or None
    starter = STARTERS_BY_KEY.get(starter_key) if starter_key else None
    if starter_key and not starter:
        raise HTTPException(status_code=422, detail="Onbekende gespreksstarter")
    if starter and not next(
        (s for s in _starter_library(db, current_user)
         if s["key"] == starter_key and s["available"]), None
    ):
        raise HTTPException(status_code=403, detail="Deze gespreksstarter is niet beschikbaar")
    module_key = (starter["module_key"] if starter else
                  (payload.get("module_key") or "general").strip())[:80]
    if module_key != "general" and module_key not in MODULE_LABELS:
        raise HTTPException(status_code=422, detail="Onbekend Copilot-onderdeel")
    title = (payload.get("title") or (starter["title"] if starter else "Nieuw gesprek"))[:300]
    from semantic_layer import _shop_scope
    sid = _shop_scope(db, payload.get("shop_id"))
    allowed_shops = authz.user_allowed_shop_ids(db, current_user)
    if allowed_shops is not None and sid not in allowed_shops:
        raise HTTPException(status_code=403, detail="Geen toegang tot deze winkel")
    conv = models.AiConversation(
        user_id=current_user.id, shop_id=sid, title=title,
        module_key=module_key, starter_key=starter_key,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return _conversation_out(conv)


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    shop_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    conv = _own_conversation(db, current_user, conversation_id, shop_id)
    msgs = db.query(models.AiMessage).filter(
        models.AiMessage.conversation_id == conv.id
    ).order_by(models.AiMessage.id).all()
    out = _conversation_out(conv)
    out["messages"] = [_message_out(m) for m in msgs]
    return out


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    shop_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    conv = _own_conversation(db, current_user, conversation_id, shop_id)
    db.query(models.AiMessage).filter(
        models.AiMessage.conversation_id == conv.id).delete()
    db.delete(conv)
    db.commit()
    return {"message": "Gesprek verwijderd"}


@router.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: int,
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    shop_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Stel een vraag aan de Copilot. Antwoord als SSE-stream:
      data: {"type":"status"|"tool"|"answer"|"done", ...}
    Fail-safe (§56): bij LLM-storing komt een gestructureerd foutantwoord,
    nooit een 500.
    """
    # PII-maskering aan de ingang (§31): e-mail/telefoon in de vraag wordt
    # gemaskeerd vóór opslag én vóór verzending richting het model.
    question = ai_gateway.pii_scrub((payload.get("content") or "").strip())
    if not question:
        raise HTTPException(status_code=400, detail="content is verplicht")
    if len(question) > 4000:
        raise HTTPException(status_code=400, detail="Vraag is te lang (max 4000 tekens)")

    conv = _own_conversation(db, current_user, conversation_id, shop_id)

    # Global Filter Context (taak 220): de frontend stuurt de actieve
    # hiërarchie-selectie mee als default scope voor de tooldata. Alleen
    # integere node-ids worden geaccepteerd; autorisatie blijft server-side
    # (de semantic layer filtert enkel op actieve assignments).
    ctx = payload.get("context") or {}
    hierarchy_node_ids: list[int] = []
    product_scope: Optional[dict] = None
    global_filter_context: dict = {}
    if isinstance(ctx, dict):
        # Niet-hiërarchische filters worden als gecontroleerde context aan het
        # model doorgegeven. Tools passen alleen ondersteunde parameters toe;
        # de prompt verplicht de Copilot beperkingen expliciet te melden.
        for key in ("brands", "statuses"):
            values = ctx.get(key)
            if isinstance(values, list):
                cleaned = [
                    str(v)[:255] for v in values if isinstance(v, str)
                ][:100]
                if cleaned:
                    global_filter_context[key] = cleaned
        sku_query = ctx.get("sku_query")
        if isinstance(sku_query, str) and sku_query.strip():
            global_filter_context["sku_query"] = sku_query.strip()[:100]
        period_days = ctx.get("period_days")
        if isinstance(period_days, int) and 1 <= period_days <= 3650:
            global_filter_context["period_days"] = period_days
        raw_ids = ctx.get("hierarchy_node_ids") or []
        if isinstance(raw_ids, list):
            hierarchy_node_ids = [int(v) for v in raw_ids[:50]
                                  if isinstance(v, (int, str))
                                  and str(v).lstrip("-").isdigit()]
        # Cascaderend Product-filter (taak #301): expliciete productscope.
        # Alleen sku_id + label worden geaccepteerd; het label wordt server-side
        # opnieuw opgezocht zodat de modelcontext nooit client-gestuurd is.
        raw_prod = ctx.get("product")
        if isinstance(raw_prod, dict) and isinstance(raw_prod.get("sku_id"), str):
            sku = raw_prod["sku_id"][:100]
            # Shop-autorisatie: een SKU buiten de toegestane winkels van de
            # gebruiker wordt genegeerd (geen productnamen van andere shops
            # in de modelcontext).
            p = product_scope_service.get_scoped_product(
                db, sku, authz.user_allowed_shop_ids(db, current_user))
            if p is not None:
                product_scope = {"sku_id": p.sku_id,
                                 "label": f"SKU {p.sku_id} – {p.product_name}",
                                 "source": "global_filter"}

    # Atomische budgetreservering vóór de SSE-stream (§34): gooit 429 als het
    # dagbudget op is. Hier (vóór StreamingResponse) zodat de client een echte
    # 429 ontvangt, niet een generiek SSE-foutantwoord na een 200-header.
    # slot_date = de datum waarvoor is gereserveerd (doorgeven aan run_copilot
    # voor correcte reconciliatie bij calls die om middernacht eindigen).
    # max_tokens = de dagelijkse tokenlimiet voor deze gebruiker (voor per-ronde
    # controle in run_copilot zodat overruns door grote tool-output worden gestopt).
    # budget_warning: melding als de gebruiker ≥ 80% van zijn dagbudget heeft
    # verbruikt; wordt via answer.warnings zichtbaar in het Copilot-antwoord.
    slot_date, max_tokens, budget_warning = ai_gateway.check_and_reserve_budget(
        current_user.username, current_user.role
    )

    # Geschiedenis vóór het opslaan van de nieuwe vraag
    prior = db.query(models.AiMessage).filter(
        models.AiMessage.conversation_id == conv.id
    ).order_by(models.AiMessage.id).all()
    history = [{"role": m.role, "content": m.content} for m in prior]

    # Vraag opslaan; titel afleiden van de eerste vraag.
    # Als de opslag mislukt, geef de slot-reservering terug zodat het dagbudget
    # niet wordt uitgeput door een mislukte opslaagtransactie.
    try:
        db.add(models.AiMessage(conversation_id=conv.id, role="user", content=question))
        # Handmatige lege gesprekken krijgen hun eerste vraag als titel.
        # Gecureerde starters behouden de korte, herkenbare bibliotheektitel.
        if not prior and not conv.starter_key:
            conv.title = question[:300]
        db.commit()
    except Exception:
        ai_gateway.release_budget_slot_reservation(db, current_user.username, slot_date)
        raise

    # Lange gesprekken: samenvatting van oudere berichten meesturen (leerloop)
    history_summary = ai_gateway.get_history_summary(db, conv.id)

    # Volg bij of de generator minstens één keer is geïtereerd door Starlette.
    # Als de client vóór de eerste byte disconnecteert, is de generator nooit
    # gestart en loopt run_copilot's finally niet → cleanup via background task.
    _generator_started: list[bool] = [False]

    def _release_if_never_started() -> None:
        """Achtergrondtaak: geef reservering terug als de generator nooit liep."""
        if not _generator_started[0]:
            release_db = ai_gateway.SessionLocal()
            try:
                ai_gateway.release_budget_slot_reservation(
                    release_db, current_user.username, slot_date
                )
            finally:
                release_db.close()

    def event_stream():
        _generator_started[0] = True
        final_answer = None
        try:
            for event in ai_gateway.run_copilot(
                db, current_user, history, question,
                conversation_id=conv.id,
                # Shop-scope server-side uit het gesprek — nooit uit modeloutput
                shop_id=conv.shop_id,
                history_summary=history_summary,
                slot_date=slot_date,
                max_tokens=max_tokens,
                budget_warning=budget_warning,
                hierarchy_node_ids=hierarchy_node_ids or None,
                product_scope=product_scope,
                global_filter_context=global_filter_context or None,
            ):
                if event.get("type") == "answer":
                    final_answer = event["answer"]
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception:
            # Extra vangnet: de stream mag nooit hard breken
            final_answer = final_answer or {
                "conclusion": "Er ging iets mis bij het genereren van het antwoord.",
                "warnings": ["Onverwachte fout in de AI Gateway."],
                "confidence": 0.0, "limitations": [], "sources": [],
                "records": 0, "period": None, "data_freshness": None,
                "suggested_action": None, "links": [],
            }
            yield f"data: {json.dumps({'type': 'answer', 'answer': final_answer}, default=str)}\n\n"
        # Assistant-antwoord persisteren voor de gespreksgeschiedenis
        assistant_message_id = None
        try:
            if final_answer:
                msg = models.AiMessage(
                    conversation_id=conv.id, role="assistant",
                    content=final_answer.get("conclusion") or "",
                    answer_json=final_answer,
                )
                db.add(msg)
                conv.updated_at = models.datetime.utcnow()
                db.commit()
                assistant_message_id = msg.id
        except Exception:
            db.rollback()
        yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_message_id})}\n\n"
        # Leerloop (fail-safe, na het antwoord): samenvatting van lange
        # gesprekken + extractie van duurzame voorkeuren (§ leerloop)
        try:
            ai_gateway.maybe_summarize_conversation(db, current_user, conv.id)
            ai_gateway.maybe_extract_memory(db, current_user, conv.id)
        except Exception:
            pass

    # Achtergrondtaak: geef reservering terug als de generator nooit is gestart
    # (client-disconnect vóór eerste byte, of pre-stream fout na message-save).
    background_tasks.add_task(_release_if_never_started)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Providerbeheer (Task #79): Replit AI vs. eigen OpenAI-sleutel ───────────

@router.get("/provider")
def get_provider_status(
    _: models.User = Depends(auth_utils.require_role("admin")),
    db: Session = Depends(get_db),
):
    """Actieve AI-provider + configuratiestatus van beide opties (admin)."""
    overview = ai_gateway.provider_overview()
    row = db.query(models.AiProviderSetting).order_by(
        models.AiProviderSetting.id).first()
    overview["updated_at"] = row.updated_at.isoformat() if row and row.updated_at else None
    overview["updated_by"] = row.updated_by if row else None
    return overview


@router.put("/provider")
def switch_provider(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    """Wissel expliciet van AI-provider (admin). De keuze wordt persistent
    opgeslagen en overleeft een herstart. `provider=null` → automatisch
    (Replit AI zodra geconfigureerd, anders eigen sleutel)."""
    provider = payload.get("provider")
    if provider is not None and provider not in ai_gateway.KNOWN_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Onbekende provider; kies uit {list(ai_gateway.KNOWN_PROVIDERS)} of null (automatisch)",
        )
    warning = None
    if provider is not None and not ai_gateway.provider_configured(provider):
        # Bewuste keuze toestaan, maar nooit stil: de dienst is dan expliciet
        # 'niet beschikbaar' totdat de provider geconfigureerd is.
        warning = (
            f"Provider '{provider}' is nog niet geconfigureerd; de Copilot is "
            "niet beschikbaar totdat de bijbehorende sleutel/omgeving is ingesteld."
        )
    ai_gateway.set_active_provider(db, provider, updated_by=current_user.username)
    out = ai_gateway.provider_overview()
    out["warning"] = warning
    return out


@router.post("/provider/test")
def test_provider(
    payload: dict = Body(default={}),
    _: models.User = Depends(auth_utils.require_role("admin")),
):
    """Live verbindingstest voor één provider (admin). Verbruikt geen tokens."""
    provider = payload.get("provider")
    if provider not in ai_gateway.KNOWN_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"provider is verplicht; kies uit {list(ai_gateway.KNOWN_PROVIDERS)}",
        )
    reachable, error = ai_gateway.probe_provider(force=True, provider=provider)
    return {
        "provider": provider,
        "configured": ai_gateway.provider_configured(provider),
        "reachable": reachable,
        "error": error,
    }


@router.get("/model-calls")
def list_model_calls(
    limit: int = 50,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.require_role("admin", "pricing_manager", "analyst")),
):
    """AI Gateway-logboek (§32): laatste model-calls met tokenverbruik."""
    limit = max(1, min(limit, 200))
    rows = db.query(models.AiModelCall).order_by(
        desc(models.AiModelCall.timestamp)).limit(limit).all()
    return [{
        "id": r.id,
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "username": r.username, "user_role": r.user_role,
        "conversation_id": r.conversation_id, "purpose": r.purpose,
        "provider": r.provider, "model": r.model,
        "functions_called": r.functions_called, "datasources": r.datasources,
        "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
        "total_tokens": r.total_tokens, "llm_roundtrips": r.llm_roundtrips,
        "duration_ms": r.duration_ms, "status": r.status,
        "error_message": r.error_message,
    } for r in rows]

@router.get("/budget/config")
def list_budget_configs(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.require_role("admin")),
):
    """Haal alle geconfigureerde AI-budgetten op (admin)."""
    rows = db.query(models.AiBudgetConfig).order_by(
        models.AiBudgetConfig.username.nullsfirst()
    ).all()
    return [{
        "id": r.id,
        "username": r.username,  # None = globale standaard
        "max_calls_per_day": r.max_calls_per_day,
        "max_tokens_per_day": r.max_tokens_per_day,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "updated_by": r.updated_by,
    } for r in rows]


# ─── Copilot-geheugen: inzien en corrigeren (Task #44) ───────────────────────

MEMORY_MANAGER_ROLES = ("admin", "pricing_manager")


def _memory_out(m: models.AiUserMemory) -> dict:
    return {
        "id": m.id,
        "key": m.key,
        "value": m.value,
        "scope": "organisatie" if m.user_id is None else "persoonlijk",
        "source_conversation_id": m.source_conversation_id,
        "source": m.source or "extracted",
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def _memory_item_for_edit(
    db: Session, user: models.User, memory_id: int
) -> models.AiUserMemory:
    """Haal een geheugen-item op met RBAC voor bewerken/verwijderen:
    eigen items altijd; organisatie-items (user_id NULL) alleen voor
    admin/pricing_manager. Items van andere gebruikers → 404 (geen lek)."""
    row = db.query(models.AiUserMemory).filter(
        models.AiUserMemory.id == memory_id).first()
    if row is not None and (row.status or "active") == "deleted":
        # Tombstones zijn onzichtbaar voor de gebruiker (Task #135).
        row = None
    if not row or (row.user_id is not None and row.user_id != user.id):
        raise HTTPException(status_code=404, detail="Geheugen-item niet gevonden")
    if row.user_id is None and user.role not in MEMORY_MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Organisatie-brede geheugen-items kunnen alleen door "
                   "admin of pricing_manager worden beheerd",
        )
    return row


@router.get("/memory")
def list_memory(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Wat de Copilot over je onthoudt: eigen items + organisatie-brede items.
    `editable` geeft aan of de huidige gebruiker het item mag wijzigen."""
    rows = (db.query(models.AiUserMemory)
            .filter((models.AiUserMemory.user_id == current_user.id) |
                    (models.AiUserMemory.user_id.is_(None)),
                    models.AiUserMemory.status == "active")
            .order_by(desc(models.AiUserMemory.updated_at)).all())
    can_manage_org = current_user.role in MEMORY_MANAGER_ROLES
    out = []
    for r in rows:
        item = _memory_out(r)
        item["editable"] = r.user_id is not None or can_manage_org
        out.append(item)
    return out

@router.get("/memory/deleted")
def list_deleted_memory(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Verwijderde geheugen-items (tombstones) die de gebruiker mag herstellen:
    eigen items + (voor admin/pricing_manager) organisatie-brede items."""
    can_manage_org = current_user.role in MEMORY_MANAGER_ROLES
    q = db.query(models.AiUserMemory).filter(
        models.AiUserMemory.status == "deleted")
    if can_manage_org:
        q = q.filter((models.AiUserMemory.user_id == current_user.id) |
                     (models.AiUserMemory.user_id.is_(None)))
    else:
        q = q.filter(models.AiUserMemory.user_id == current_user.id)
    rows = q.order_by(desc(models.AiUserMemory.updated_at)).all()
    out = []
    for r in rows:
        item = _memory_out(r)
        item["editable"] = True
        out.append(item)
    return out
@router.post("/memory")
def create_memory(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Voeg zelf een voorkeur toe aan het Copilot-geheugen.

    Scope: "persoonlijk" (default) of "organisatie" — organisatie-breed alleen
    voor admin/pricing_manager (zelfde RBAC als bewerken). Bestaat de key al
    binnen dezelfde scope, dan wordt de waarde bijgewerkt (upsert)."""
    key = (payload.get("key") or "").strip()[:200]
    value = ai_gateway.pii_scrub((payload.get("value") or "").strip())[:2000]
    scope = (payload.get("scope") or "persoonlijk").strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="key is verplicht")
    if not value:
        raise HTTPException(status_code=400, detail="value is verplicht")
    if scope not in ("persoonlijk", "organisatie"):
        raise HTTPException(
            status_code=400,
            detail="scope moet 'persoonlijk' of 'organisatie' zijn")
    if scope == "organisatie" and current_user.role not in MEMORY_MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Organisatie-brede geheugen-items kunnen alleen door "
                   "admin of pricing_manager worden toegevoegd",
        )
    user_id = None if scope == "organisatie" else current_user.id
    existing = db.query(models.AiUserMemory).filter(
        models.AiUserMemory.user_id.is_(None) if user_id is None
        else models.AiUserMemory.user_id == user_id,
        models.AiUserMemory.key == key,
    ).first()
    if existing:
        existing.value = value
        # Een tombstone (status="deleted") wordt door een handmatige upsert
        # weer geactiveerd — de gebruiker maakt de key bewust opnieuw aan.
        existing.status = "active"
        existing.source = "manual"
        existing.updated_at = models.datetime.utcnow()
        db.commit()
        db.refresh(existing)
        item = _memory_out(existing)
        item["editable"] = True
        return item
    row = models.AiUserMemory(user_id=user_id, key=key, value=value,
                              source="manual")
    db.add(row)
    db.commit()
    db.refresh(row)
    item = _memory_out(row)
    item["editable"] = True
    return item
@router.put("/memory/{memory_id}")
def update_memory(
    memory_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Corrigeer een geheugen-item (eigen items; organisatie-items admin/pm)."""
    row = _memory_item_for_edit(db, current_user, memory_id)
    value = ai_gateway.pii_scrub((payload.get("value") or "").strip())[:2000]
    if not value:
        raise HTTPException(status_code=400, detail="value is verplicht")
    row.value = value
    # Handmatig gecorrigeerde waarden winnen voortaan van automatische
    # extractie (Task #135).
    row.source = "manual"
    row.updated_at = models.datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _memory_out(row)


@router.delete("/memory/{memory_id}")
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Verwijder een geheugen-item (eigen items; organisatie-items admin/pm)."""
    row = _memory_item_for_edit(db, current_user, memory_id)
    # Soft-delete (tombstone): de rij blijft bestaan met status="deleted"
    # zodat automatische extractie dezelfde key niet stilletjes opnieuw
    # aanmaakt (Task #135). Onzichtbaar in lijst en context.
    row.status = "deleted"
    row.updated_at = models.datetime.utcnow()
    db.commit()
    return {"message": "Geheugen-item verwijderd"}


# ─── Leerloop: feedback, FAQ en kwaliteitsdashboard ──────────────────────────

@router.post("/messages/{message_id}/feedback")
def give_feedback(
    message_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Beoordeel één Copilot-antwoord (duim omhoog/omlaag + toelichting).
    Eén feedback per gebruiker per antwoord (upsert). Negatieve feedback
    genereert automatisch een verbetersuggestie-item in de backlog."""
    score = payload.get("score")
    if score not in (1, -1):
        raise HTTPException(status_code=400, detail="score moet 1 of -1 zijn")
    comment = (payload.get("comment") or "").strip()[:2000] or None

    msg = db.query(models.AiMessage).filter(models.AiMessage.id == message_id).first()
    if not msg or msg.role != "assistant":
        raise HTTPException(status_code=404, detail="Antwoord niet gevonden")
    _own_conversation(db, current_user, msg.conversation_id)

    # Context: de vraag vóór dit antwoord + gebruikte tools + promptversie
    prev_q = db.query(models.AiMessage).filter(
        models.AiMessage.conversation_id == msg.conversation_id,
        models.AiMessage.role == "user",
        models.AiMessage.id < msg.id,
    ).order_by(desc(models.AiMessage.id)).first()
    answer = msg.answer_json or {}
    tools = [s.get("function") for s in (answer.get("sources") or [])
             if isinstance(s, dict) and s.get("function")]

    fb = db.query(models.AiFeedback).filter(
        models.AiFeedback.message_id == msg.id,
        models.AiFeedback.user_id == current_user.id,
    ).first()
    created = fb is None
    if fb is None:
        fb = models.AiFeedback(message_id=msg.id, user_id=current_user.id)
        db.add(fb)
    fb.conversation_id = msg.conversation_id
    fb.username = current_user.username
    fb.score = score
    fb.comment = comment
    fb.question = prev_q.content if prev_q else None
    fb.answer_excerpt = msg.content
    fb.tools_used = tools
    fb.prompt_version_id = answer.get("prompt_version_id")
    db.commit()
    db.refresh(fb)

    # Kwaliteitsloop: negatieve feedback → verbetersuggestie (menselijke
    # goedkeuring via de governance-backlog, geen automatisch herschrijven)
    if score == -1:
        marker = f"[copilot-feedback #{fb.id}]"
        exists = db.query(models.BacklogItem).filter(
            models.BacklogItem.module_key == "ai_copilot",
            models.BacklogItem.description.like(f"%{marker}%"),
        ).first()
        if not exists:
            q_txt = (fb.question or "(onbekende vraag)")[:200]
            db.add(models.BacklogItem(
                module_key="ai_copilot",
                title=f"Copilot-verbetersuggestie: negatief beoordeeld antwoord op '{q_txt}'"[:500],
                description=(
                    f"{marker} Automatisch aangemaakt door de Copilot-kwaliteitsloop.\n\n"
                    f"Vraag: {fb.question or '-'}\n\n"
                    f"Antwoord: {(fb.answer_excerpt or '-')[:1500]}\n\n"
                    f"Toelichting gebruiker: {comment or '-'}\n"
                    f"Gebruikte tools: {', '.join(tools) or '-'}\n"
                    f"Promptversie-id: {fb.prompt_version_id or '-'}\n\n"
                    "Beoordeel of de systeemprompt (PromptVersion ai_copilot) of de "
                    "tooling moet worden aangepast; wijzigingen via governance."
                ),
                item_type="improvement", status="open", priority="medium",
                created_by="copilot_quality_loop",
            ))
            db.commit()

    return {"id": fb.id, "message_id": msg.id, "score": fb.score,
            "comment": fb.comment, "created": created}


@router.get("/faq")
def frequently_asked(
    limit: int = 10,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.get_current_user),
):
    """'Vaker gesteld'-overzicht: meest voorkomende vragen (organisatie-breed,
    genormaliseerd op kleine letters)."""
    limit = max(1, min(limit, 50))
    norm = func.lower(func.trim(models.AiMessage.content))
    rows = (db.query(norm.label("q"), func.count(models.AiMessage.id).label("n"),
                     func.max(models.AiMessage.created_at).label("last"))
            .filter(models.AiMessage.role == "user")
            .group_by(norm).order_by(desc("n"), desc("last")).limit(limit).all())
    return {"questions": [
        {"question": r.q, "count": int(r.n),
         "last_asked": r.last.isoformat() if r.last else None}
        for r in rows if r.q
    ]}


@router.get("/quality")
def quality_dashboard(
    weeks: int = 12,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.require_role("admin", "pricing_manager", "analyst")),
):
    """Kwaliteitsdashboard (analyst+): feedbackscore per week, per promptversie
    en per tool; laag-scorende antwoorden voor analyse (leerloop)."""
    weeks = max(1, min(weeks, 52))
    since = models.datetime.utcnow() - timedelta(weeks=weeks)
    all_fb = db.query(models.AiFeedback).filter(
        models.AiFeedback.created_at >= since).all()

    def _agg(rows):
        pos = sum(1 for r in rows if r.score > 0)
        neg = sum(1 for r in rows if r.score < 0)
        total = pos + neg
        return {"positive": pos, "negative": neg, "total": total,
                "score_pct": round(100.0 * pos / total, 1) if total else None}

    # Per ISO-week
    by_week: dict = {}
    for r in all_fb:
        iso = (r.created_at or models.datetime.utcnow()).isocalendar()
        by_week.setdefault(f"{iso[0]}-W{iso[1]:02d}", []).append(r)
    weekly = [{"week": w, **_agg(rows)} for w, rows in sorted(by_week.items())]

    # Per promptversie (vergelijking van versies op feedbackscore)
    versions = {p.id: p for p in db.query(models.PromptVersion).filter(
        models.PromptVersion.module_key == ai_gateway.PROMPT_MODULE_KEY).all()}
    by_version: dict = {}
    for r in all_fb:
        by_version.setdefault(r.prompt_version_id, []).append(r)
    per_version = [{
        "prompt_version_id": vid,
        "version": versions[vid].version if vid in versions else None,
        "title": versions[vid].title if vid in versions else None,
        **_agg(rows),
    } for vid, rows in sorted(by_version.items(), key=lambda t: (t[0] is None, t[0]))]

    # Per tool
    by_tool: dict = {}
    for r in all_fb:
        for t in (r.tools_used or []):
            by_tool.setdefault(t, []).append(r)
    per_tool = [{"tool": t, **_agg(rows)} for t, rows in sorted(by_tool.items())]

    # Laag-scorende antwoorden (drill-down voor analyse)
    low = (db.query(models.AiFeedback)
           .filter(models.AiFeedback.score < 0)
           .order_by(desc(models.AiFeedback.created_at)).limit(50).all())
    low_out = [{
        "feedback_id": r.id, "message_id": r.message_id,
        "conversation_id": r.conversation_id, "username": r.username,
        "question": r.question, "answer_excerpt": (r.answer_excerpt or "")[:500],
        "comment": r.comment, "tools_used": r.tools_used,
        "prompt_version_id": r.prompt_version_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in low]

    suggestions_open = db.query(func.count(models.BacklogItem.id)).filter(
        models.BacklogItem.module_key == "ai_copilot",
        models.BacklogItem.created_by == "copilot_quality_loop",
        models.BacklogItem.status == "open",
    ).scalar() or 0

    return {
        "period_weeks": weeks,
        "overall": _agg(all_fb),
        "weekly": weekly,
        "per_prompt_version": per_version,
        "per_tool": per_tool,
        "low_scoring": low_out,
        "open_improvement_suggestions": int(suggestions_open),
    }

@router.get("/budget/me")
def budget_usage_me(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """
    Eigen AI-dagbudgetverbruik van vandaag (§34, Task #121).
    Compact overzicht voor de verbruiksindicator in het Copilot-scherm:
    gebruikte calls/tokens versus de effectieve limiet.
    """
    today = date.today()
    max_calls, max_tokens = ai_gateway._get_budget_config(db, current_user.username)

    slot = db.query(models.AiBudgetSlot).filter(
        models.AiBudgetSlot.username == current_user.username,
        models.AiBudgetSlot.slot_date == today,
    ).first()

    calls_used = slot.calls_reserved if slot else 0
    # Gereserveerde tokens zijn een tijdelijke worst-case-claim; toon het
    # werkelijke verbruik zodra dat gereconcilieerd is, anders de reservering.
    tokens_used = max(slot.tokens_actual or 0, 0) if slot else 0
    tokens_reserved = slot.tokens_reserved if slot else 0

    # Autoritatieve toelatingsstatus (Task #159): dezelfde regel als
    # check_and_reserve_budget, inclusief de upfront-tokenreservering per call.
    # De frontend gebruikt dit om het vraagveld vriendelijk te blokkeren.
    exhausted = (
        (max_calls is not None and calls_used >= max_calls)
        or (
            max_tokens is not None
            and tokens_reserved + ai_gateway._UPFRONT_TOKEN_RESERVATION > max_tokens
        )
    )

    return {
        "exhausted": exhausted,
        "date": today.isoformat(),
        "calls_used": calls_used,
        "max_calls_per_day": max_calls,
        "calls_pct": round(calls_used / max_calls * 100, 1) if max_calls else None,
        "tokens_used": tokens_used,
        "tokens_reserved": tokens_reserved,
        "max_tokens_per_day": max_tokens,
        "tokens_pct": round(tokens_reserved / max_tokens * 100, 1) if max_tokens else None,
    }
@router.get("/budget/usage")
def budget_usage_today(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.require_role("admin")),
):
    """
    Verbruiksoverzicht voor vandaag vanuit de reserveringsslots (§34).
    Toont per gebruiker: gereserveerde calls/tokens, werkelijk verbruik en limiet.
    """
    today = date.today()

    # Overschrijdingen tellen vanuit AiModelCall
    exceeded_rows = db.query(
        models.AiModelCall.username,
        func.sum(
            case((models.AiModelCall.status == "budget_exceeded", 1), else_=0)
        ).label("exceeded_count"),
    ).filter(
        func.date(models.AiModelCall.timestamp) == today,
    ).group_by(models.AiModelCall.username).all()
    exceeded_map = {r.username: int(r.exceeded_count or 0) for r in exceeded_rows}

    # Slot-tabel als primaire bron voor gereserveerde counts
    slots = db.query(models.AiBudgetSlot).filter(
        models.AiBudgetSlot.slot_date == today,
    ).all()

    result = []
    for slot in slots:
        username = slot.username
        max_calls, max_tokens = ai_gateway._get_budget_config(db, username)
        result.append({
            "username": username,
            "calls_reserved": slot.calls_reserved,
            "tokens_reserved": slot.tokens_reserved,
            "tokens_actual": slot.tokens_actual,
            "budget_exceeded_count": exceeded_map.get(username, 0),
            "max_calls_per_day": max_calls,
            "max_tokens_per_day": max_tokens,
            "calls_pct": round(slot.calls_reserved / max_calls * 100, 1) if max_calls else None,
            "tokens_pct": round(slot.tokens_reserved / max_tokens * 100, 1) if max_tokens else None,
        })
    return {"date": today.isoformat(), "users": result}

@router.delete("/budget/config/{config_id}")
def delete_budget_config(
    config_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth_utils.require_role("admin")),
):
    """Verwijder een budgetlimiet (admin)."""
    row = db.query(models.AiBudgetConfig).filter(
        models.AiBudgetConfig.id == config_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Budgetconfiguratie niet gevonden")
    db.delete(row)
    db.commit()
    return {"message": "Budgetconfiguratie verwijderd"}

@router.put("/budget/config")
def upsert_budget_config(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin")),
):
    """
    Maak een budgetlimiet aan of update hem.
    Body: { username?: string|null, max_calls_per_day?: int|null, max_tokens_per_day?: int|null }
    username=null → globale standaard; weglaten van een veld behoudt de huidige waarde.
    """
    username = payload.get("username")  # None of een string
    row = db.query(models.AiBudgetConfig).filter(
        models.AiBudgetConfig.username == username
        if username is not None
        else models.AiBudgetConfig.username.is_(None)
    ).first()
    if row is None:
        row = models.AiBudgetConfig(username=username)
        db.add(row)

    if "max_calls_per_day" in payload:
        v = payload["max_calls_per_day"]
        if v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="max_calls_per_day moet een geheel getal zijn")
            if v < 1:
                raise HTTPException(status_code=422, detail="max_calls_per_day moet minimaal 1 zijn")
        row.max_calls_per_day = v
    if "max_tokens_per_day" in payload:
        v = payload["max_tokens_per_day"]
        if v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="max_tokens_per_day moet een geheel getal zijn")
            min_tokens = ai_gateway._UPFRONT_TOKEN_RESERVATION
            if v < min_tokens:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"max_tokens_per_day moet minimaal {min_tokens:,} zijn "
                        f"(de upfront-reservering per verzoek). "
                        "Een lagere waarde zou alle verzoeken permanent blokkeren."
                    ),
                )
        row.max_tokens_per_day = v
    row.updated_by = current_user.username

    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "username": row.username,
        "max_calls_per_day": row.max_calls_per_day,
        "max_tokens_per_day": row.max_tokens_per_day,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by": row.updated_by,
    }

@router.post("/memory/{memory_id}/restore")
def restore_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Herstel een verwijderd geheugen-item: status terug naar "active",
    waarna automatische extractie de key weer mag bijwerken."""
    row = db.query(models.AiUserMemory).filter(
        models.AiUserMemory.id == memory_id).first()
    if not row or (row.user_id is not None and row.user_id != current_user.id):
        raise HTTPException(status_code=404, detail="Geheugen-item niet gevonden")
    if row.user_id is None and current_user.role not in MEMORY_MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Organisatie-brede geheugen-items kunnen alleen door "
                   "admin of pricing_manager worden beheerd",
        )
    if (row.status or "active") != "deleted":
        raise HTTPException(
            status_code=409, detail="Geheugen-item is niet verwijderd")
    row.status = "active"
    row.updated_at = models.datetime.utcnow()
    db.commit()
    db.refresh(row)
    item = _memory_out(row)
    item["editable"] = True
    return item
