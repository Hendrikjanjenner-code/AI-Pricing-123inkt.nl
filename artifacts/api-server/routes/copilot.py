"""
Commercial AI Copilot routes (§26) — /api/copilot/...

Chat met gespreksgeschiedenis; elk antwoord loopt via de AI Gateway
(ai_gateway.py) en is dus beperkt tot approved semantic-layer-functies.
"""
import json
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
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
    """Beschikbaarheid van de AI-dienst + voorbeeldvragen (§26)."""
    return {
        "ai_available": ai_gateway.ai_available(),
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

    # Geschiedenis vóór het opslaan van de nieuwe vraag
    prior = db.query(models.AiMessage).filter(
        models.AiMessage.conversation_id == conv.id
    ).order_by(models.AiMessage.id).all()
    history = [{"role": m.role, "content": m.content} for m in prior]

    # Vraag opslaan; titel afleiden van de eerste vraag
    db.add(models.AiMessage(conversation_id=conv.id, role="user", content=question))
    if not prior:
        conv.title = question[:300]
    db.commit()

    def event_stream():
        final_answer = None
        try:
            for event in ai_gateway.run_copilot(
                db, current_user, history, question,
                conversation_id=conv.id,
                # Shop-scope server-side uit het gesprek — nooit uit modeloutput
                shop_id=conv.shop_id,
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
        try:
            if final_answer:
                db.add(models.AiMessage(
                    conversation_id=conv.id, role="assistant",
                    content=final_answer.get("conclusion") or "",
                    answer_json=final_answer,
                ))
                conv.updated_at = models.datetime.utcnow()
                db.commit()
        except Exception:
            db.rollback()
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

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
