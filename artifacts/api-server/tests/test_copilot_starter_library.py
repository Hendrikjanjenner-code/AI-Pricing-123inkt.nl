"""Regressietests voor de gecureerde Copilot-gespreksbibliotheek."""
import os
import sys
from datetime import date
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from main import app
import models
from database import SessionLocal
from semantic_layer import get_competitor_ranking, get_price_position


def _headers(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"username": "dev_admin", "password": "admin123"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_status_contains_grouped_starters_and_five_competition_questions():
    with TestClient(app) as client:
        response = client.get("/api/copilot/status", headers=_headers(client))
        assert response.status_code == 200, response.text
        data = response.json()
        starters = data["starter_library"]
        competition = [s for s in starters if s["module_key"] == "competition"]
        assert len(competition) >= 5
        assert len(data["example_questions"]) >= 5
        assert all(s["module_label"] == "Concurrentie" for s in competition)
        assert all(isinstance(s["available"], bool) for s in starters)
        assert {
            "competition", "pricing", "assortment", "sales", "forecast",
            "data_quality", "management",
        }.issubset({s["module_key"] for s in starters})


def test_starter_creates_metadata_and_meaningful_history_title():
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/copilot/conversations",
            headers=headers,
            json={
                "starter_key": "competitors-attention",
                "module_key": "competition",
            },
        )
        assert created.status_code == 200, created.text
        conversation = created.json()
        try:
            assert conversation["title"] == "Belangrijkste concurrenten"
            assert conversation["module_key"] == "competition"
            assert conversation["module_label"] == "Concurrentie"
            assert conversation["starter_key"] == "competitors-attention"

            listed = client.get("/api/copilot/conversations?shop_id=1", headers=headers)
            assert listed.status_code == 200
            same = next(c for c in listed.json() if c["id"] == conversation["id"])
            assert same["module_label"] == "Concurrentie"
        finally:
            deleted = client.delete(
                f"/api/copilot/conversations/{conversation['id']}?shop_id=1",
                headers=headers,
            )
            assert deleted.status_code == 200


def test_unknown_starter_and_module_are_rejected():
    with TestClient(app) as client:
        headers = _headers(client)
        unknown_starter = client.post(
            "/api/copilot/conversations",
            headers=headers,
            json={"starter_key": "bestaat-niet"},
        )
        assert unknown_starter.status_code == 422
        unknown_module = client.post(
            "/api/copilot/conversations",
            headers=headers,
            json={"module_key": "bestaat-niet"},
        )
        assert unknown_module.status_code == 422


def test_conversations_and_competition_scores_stay_inside_active_shop():
    suffix = uuid4().hex[:10]
    db = SessionLocal()
    shop = models.DimShop(
        shop_code=f"copilot-{suffix}", name=f"Copilot test {suffix}",
        is_default=False, active=True,
    )
    db.add(shop)
    db.flush()
    sku = f"COPILOT-{suffix}"
    product = models.DimProduct(
        sku_id=sku, product_name="Copilot shop-scope product", shop_id=shop.id,
    )
    influence = models.CompetitorInfluenceScore(
        sku_id=sku, competitor_name=f"Concurrent {suffix}",
        run_date=date.today(), cis_score=95, csrs_score=90,
    )
    position = models.SkuCompetitionScore(
        shop_id=shop.id, sku_id=sku, run_date=date.today(),
        pcis_score=80, price_index=1.1,
    )
    db.add_all([product, influence, position])
    db.commit()

    conversation_id = None
    try:
        admin = db.query(models.User).filter(models.User.username == "dev_admin").one()
        own_rank = get_competitor_ranking(db, admin, shop_id=shop.id)
        assert own_rank["shop_scope_applied"] is True
        assert any(c["competitor_name"] == f"Concurrent {suffix}"
                   for c in own_rank["competitors"])
        assert get_price_position(db, admin, sku, shop_id=shop.id)["data_available"] is True
        assert get_price_position(db, admin, sku, shop_id=1)["data_available"] is False

        with TestClient(app) as client:
            headers = _headers(client)
            created = client.post(
                "/api/copilot/conversations",
                headers=headers,
                json={"shop_id": shop.id},
            )
            assert created.status_code == 200, created.text
            conversation_id = created.json()["id"]
            assert created.json()["shop_id"] == shop.id
            assert not any(
                c["id"] == conversation_id
                for c in client.get(
                    "/api/copilot/conversations?shop_id=1", headers=headers
                ).json()
            )
            assert client.get(
                f"/api/copilot/conversations/{conversation_id}?shop_id=1",
                headers=headers,
            ).status_code == 404
            assert client.delete(
                f"/api/copilot/conversations/{conversation_id}?shop_id={shop.id}",
                headers=headers,
            ).status_code == 200
            conversation_id = None
    finally:
        if conversation_id is not None:
            db.query(models.AiMessage).filter(
                models.AiMessage.conversation_id == conversation_id
            ).delete(synchronize_session=False)
            db.query(models.AiConversation).filter(
                models.AiConversation.id == conversation_id
            ).delete(synchronize_session=False)
        db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id == sku
        ).delete(synchronize_session=False)
        db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.sku_id == sku
        ).delete(synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == sku
        ).delete(synchronize_session=False)
        db.query(models.DimShop).filter(
            models.DimShop.id == shop.id
        ).delete(synchronize_session=False)
        db.commit()
        db.close()