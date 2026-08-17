"""
Copilot-leerloop (taak: lerende Copilot):
- Feedbackopslag: score/toelichting gekoppeld aan message, tools, promptversie;
  negatieve feedback genereert een verbetersuggestie-backlogitem.
- Geheugeninjectie: AiUserMemory-items komen als systeemcontext in de
  berichtenlijst richting het model.
- Promptversie-selectie: hoogste PromptVersion (module ai_copilot) wint;
  fallback seed vanuit de ingebouwde prompt.
- Few-shot-hergebruik: positief beoordeelde vergelijkbare vragen worden
  opgehaald; negatieve niet.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DISABLE_SCRAPE_SCHEDULER", "true")

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import ai_gateway
import models

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}


@pytest.fixture(scope="module")
def client():
    c = TestClient(app)
    c.__enter__()
    yield c
    try:
        c.__exit__(None, None, None)
    except Exception:
        pass


@pytest.fixture(scope="module")
def admin_headers(client):
    resp = client.post("/api/auth/login", json=ADMIN_LOGIN)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


def _admin_user(db):
    return db.query(models.User).filter(models.User.username == "dev_admin").first()


def _make_conv_with_answer(db, user, question="Waar verliezen we marge?",
                           prompt_version_id=None):
    conv = models.AiConversation(user_id=user.id, title=question)
    db.add(conv)
    db.flush()
    q = models.AiMessage(conversation_id=conv.id, role="user", content=question)
    db.add(q)
    db.flush()
    a = models.AiMessage(
        conversation_id=conv.id, role="assistant",
        content="We verliezen vooral marge in categorie Dranken.",
        answer_json={
            "conclusion": "We verliezen vooral marge in categorie Dranken.",
            "sources": [{"function": "get_margin_erosion", "records": 5}],
            "prompt_version_id": prompt_version_id,
        },
    )
    db.add(a)
    db.commit()
    return conv, q, a


# ─── Feedback ────────────────────────────────────────────────────────────────

def test_feedback_stored_and_linked(client, admin_headers, db):
    user = _admin_user(db)
    conv, q, a = _make_conv_with_answer(db, user)
    resp = client.post(f"/api/copilot/messages/{a.id}/feedback",
                       json={"score": 1, "comment": "Helder antwoord"},
                       headers=admin_headers)
    assert resp.status_code == 200, resp.text
    fb = db.query(models.AiFeedback).filter(models.AiFeedback.message_id == a.id).first()
    assert fb is not None
    assert fb.score == 1
    assert fb.comment == "Helder antwoord"
    assert fb.question == q.content
    assert fb.tools_used == ["get_margin_erosion"]
    assert fb.conversation_id == conv.id

    # Upsert: tweede beoordeling overschrijft, maakt geen tweede rij
    resp = client.post(f"/api/copilot/messages/{a.id}/feedback",
                       json={"score": -1}, headers=admin_headers)
    assert resp.status_code == 200
    rows = db.query(models.AiFeedback).filter(models.AiFeedback.message_id == a.id).all()
    db.expire_all()
    assert len(rows) == 1
    assert rows[0].score == -1


def test_negative_feedback_creates_improvement_item(client, admin_headers, db):
    user = _admin_user(db)
    marker_q = f"Testvraag negatief {uuid.uuid4().hex[:8]}"
    _conv, _q, a = _make_conv_with_answer(db, user, question=marker_q)
    resp = client.post(f"/api/copilot/messages/{a.id}/feedback",
                       json={"score": -1, "comment": "Cijfers kloppen niet"},
                       headers=admin_headers)
    assert resp.status_code == 200
    item = db.query(models.BacklogItem).filter(
        models.BacklogItem.module_key == "ai_copilot",
        models.BacklogItem.title.like(f"%{marker_q}%"),
    ).first()
    assert item is not None
    assert item.item_type == "improvement"
    assert item.created_by == "copilot_quality_loop"
    # Nogmaals negatief → geen duplicaat
    client.post(f"/api/copilot/messages/{a.id}/feedback",
                json={"score": -1}, headers=admin_headers)
    n = db.query(models.BacklogItem).filter(
        models.BacklogItem.title.like(f"%{marker_q}%")).count()
    assert n == 1


def test_feedback_invalid_score_and_foreign_message(client, admin_headers, db):
    resp = client.post("/api/copilot/messages/999999/feedback",
                       json={"score": 1}, headers=admin_headers)
    assert resp.status_code == 404
    user = _admin_user(db)
    _conv, _q, a = _make_conv_with_answer(db, user)
    resp = client.post(f"/api/copilot/messages/{a.id}/feedback",
                       json={"score": 5}, headers=admin_headers)
    assert resp.status_code == 400


# ─── Geheugeninjectie ────────────────────────────────────────────────────────

def test_memory_injected_into_messages(db):
    user = _admin_user(db)
    key = f"testvoorkeur_{uuid.uuid4().hex[:8]}"
    db.add(models.AiUserMemory(user_id=user.id, key=key, value="Dranken"))
    db.add(models.AiUserMemory(user_id=None, key=f"org_{key}", value="marge in %"))
    db.commit()
    try:
        msgs = ai_gateway.build_messages(db, user, [], "Hoe gaat het met Dranken?")
        sys_msgs = [m["content"] for m in msgs if m["role"] == "system"]
        joined = "\n".join(sys_msgs)
        assert key in joined and "Dranken" in joined
        assert f"org_{key}" in joined and "(organisatie-breed)" in joined
        # De vraag blijft het laatste bericht
        assert msgs[-1]["role"] == "user"
    finally:
        db.query(models.AiUserMemory).filter(
            models.AiUserMemory.key.in_([key, f"org_{key}"])).delete(
            synchronize_session=False)
        db.commit()


def test_history_summary_injected_for_long_threads(db):
    user = _admin_user(db)
    history = [{"role": "user", "content": f"vraag {i}"} for i in range(20)]
    msgs = ai_gateway.build_messages(db, user, history, "en nu?",
                                     history_summary="Eerder ging het over marge.")
    assert any("Samenvatting van het eerdere gesprek" in m["content"]
               for m in msgs if m["role"] == "system")
    # korte historie: geen samenvatting nodig
    msgs2 = ai_gateway.build_messages(db, user, history[:3], "en nu?",
                                      history_summary="X")
    assert not any("Samenvatting van het eerdere" in m["content"]
                   for m in msgs2 if m["role"] == "system")


# ─── Promptversie-selectie ───────────────────────────────────────────────────

def test_prompt_version_selection(db):
    text, pid, version = ai_gateway.get_active_prompt(db)
    assert text and pid is not None and version >= 1
    # Nieuwe hogere versie wint
    newer = models.PromptVersion(
        module_key=ai_gateway.PROMPT_MODULE_KEY, title=ai_gateway.PROMPT_TITLE,
        version=version + 1, prompt_text=text + "\nEXTRA-TESTREGEL",
        created_by="pytest")
    db.add(newer)
    db.commit()
    try:
        text2, pid2, version2 = ai_gateway.get_active_prompt(db)
        assert version2 == version + 1
        assert pid2 == newer.id
        assert "EXTRA-TESTREGEL" in text2
    finally:
        db.delete(newer)
        db.commit()


# ─── Few-shot-hergebruik ─────────────────────────────────────────────────────

def test_fewshot_retrieval_positive_only(db):
    user = _admin_user(db)
    tag = uuid.uuid4().hex[:8]
    conv, _q, a = _make_conv_with_answer(
        db, user, question=f"Welke concurrenten drukken onze marge het hardst {tag}?")
    db.add(models.AiFeedback(
        message_id=a.id, user_id=user.id, username=user.username, score=1,
        question=f"Welke concurrenten drukken onze marge het hardst {tag}?",
        answer_excerpt="Concurrent X drukt de marge het meest.",
        conversation_id=conv.id))
    # Negatief beoordeeld antwoord op bijna dezelfde vraag mag NIET terugkomen
    conv2, _q2, a2 = _make_conv_with_answer(
        db, user, question=f"Welke concurrenten drukken onze omzet het hardst {tag}?")
    db.add(models.AiFeedback(
        message_id=a2.id, user_id=user.id, username=user.username, score=-1,
        question=f"Welke concurrenten drukken onze omzet het hardst {tag}?",
        answer_excerpt="Fout antwoord.", conversation_id=conv2.id))
    db.commit()
    try:
        ex = ai_gateway.get_fewshot_examples(
            db, f"welke concurrenten drukken onze marge hard {tag}")
        assert any("Concurrent X" in (e["answer"] or "") for e in ex), ex
        assert not any("Fout antwoord" in (e["answer"] or "") for e in ex)
        # Irrelevante vraag: geen match met deze voorbeelden
        ex2 = ai_gateway.get_fewshot_examples(db, "zzz qqq xyz onzinvraag 12345")
        assert not any(tag in (e["question"] or "") for e in ex2)
    finally:
        db.query(models.AiFeedback).filter(
            models.AiFeedback.message_id.in_([a.id, a2.id])).delete(
            synchronize_session=False)
        db.commit()


# ─── Kwaliteitsdashboard & FAQ ───────────────────────────────────────────────

def test_quality_dashboard_rbac_and_shape(client, admin_headers):
    resp = client.get("/api/copilot/quality", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in ("overall", "weekly", "per_prompt_version", "per_tool",
                "low_scoring", "open_improvement_suggestions"):
        assert key in body
    resp = client.get("/api/copilot/quality")
    assert resp.status_code in (401, 403)


def test_faq_lists_frequent_questions(client, admin_headers, db):
    user = _admin_user(db)
    q = f"Hoe vaak gestelde testvraag {uuid.uuid4().hex[:8]}?"
    for _ in range(3):
        _make_conv_with_answer(db, user, question=q)
    resp = client.get("/api/copilot/faq?limit=50", headers=admin_headers)
    assert resp.status_code == 200
    hits = [r for r in resp.json()["questions"] if r["question"] == q.lower()]
    assert hits and hits[0]["count"] >= 3
