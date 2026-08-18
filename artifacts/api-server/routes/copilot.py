"""
Commercial AI Copilot routes (§26) — /api/copilot/...

Chat met gespreksgeschiedenis; elk antwoord loopt via de AI Gateway
(ai_gateway.py) en is dus beperkt tot approved semantic-layer-functies.
"""
import json
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

import ai_gateway
import auth as auth_utils
import models
from database import get_db

router = APIRouter(prefix="/api/copilot", tags=["copilot"])

# Voorbeeldvragen uit masterprompt §26
EXAMPLE_QUESTIONS = [
    "Welke concurrenten verdienen deze week onze aandacht?",
    "Waar verliezen we op dit moment marge?",
    "Welke producten hebben de grootste huismerkpotentie?",
    "Hoeveel switching-volume zien we van A-merk naar huismerk?",
    "Welke promotie werkte het afgelopen kwartaal het best?",
    "Hoe ontwikkelen traffic en conversie zich?",
    "Bij welke leveranciers lopen we margerisico?",
    "Wat zijn nu onze grootste kansen (opportunities)?",
    "Wat gebeurt er met omzet en marge als we SKU X 3% duurder maken?",
]


def _conversation_out(c: models.AiConversation) -> dict:
    return {
        "id": c.id,
        "title": c.title,
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


def _own_conversation(db: Session, user: models.User, conversation_id: int) -> models.AiConversation:
    conv = db.query(models.AiConversation).filter(
        models.AiConversation.id == conversation_id,
        models.AiConversation.user_id == user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Gesprek niet gevonden")
    return conv


@router.get("/status")
def copilot_status(
    _: models.User = Depends(auth_utils.get_current_user),
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
        "approved_functions": [
            {"name": name, "description": f.description}
            for name, f in ai_gateway.SEMANTIC_FUNCTIONS.items()
        ],
        "data_freshness": ai_gateway.get_data_freshness(db),
    }


@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    rows = db.query(models.AiConversation).filter(
        models.AiConversation.user_id == current_user.id
    ).order_by(desc(models.AiConversation.updated_at)).limit(100).all()
    return [_conversation_out(c) for c in rows]


@router.post("/conversations")
def create_conversation(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    title = (payload.get("title") or "Nieuw gesprek")[:300]
    conv = models.AiConversation(user_id=current_user.id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return _conversation_out(conv)


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    conv = _own_conversation(db, current_user, conversation_id)
    msgs = db.query(models.AiMessage).filter(
        models.AiMessage.conversation_id == conv.id
    ).order_by(models.AiMessage.id).all()
    out = _conversation_out(conv)
    out["messages"] = [_message_out(m) for m in msgs]
    return out


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    conv = _own_conversation(db, current_user, conversation_id)
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

    conv = _own_conversation(db, current_user, conversation_id)

    # Atomische budgetreservering vóór de SSE-stream (§34): gooit 429 als het
    # dagbudget op is. Hier (vóór StreamingResponse) zodat de client een echte
    # 429 ontvangt, niet een generiek SSE-foutantwoord na een 200-header.
    # slot_date = de datum waarvoor is gereserveerd (doorgeven aan run_copilot
    # voor correcte reconciliatie bij calls die om middernacht eindigen).
    # max_tokens = de dagelijkse tokenlimiet voor deze gebruiker (voor per-ronde
    # controle in run_copilot zodat overruns door grote tool-output worden gestopt).
    slot_date, max_tokens = ai_gateway.check_and_reserve_budget(
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
        if not prior:
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
