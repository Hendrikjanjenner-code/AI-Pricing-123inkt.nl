"""
Regressietests voor BigQuery-kostentotalen (taak 167).

Achtergrond: get_cost_summary gaf ooit stilletjes nul terug omdat
SUM(bytes_scanned) uit PostgreSQL als Decimal komt en de deling door een
float een exception gooide die in het fail-safe pad werd afgevangen.
Deze tests borgen dat een geschreven kostenrij daadwerkelijk zichtbaar
wordt in GET /api/bigquery/costs en meetelt in de platform-scenario's.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from main import app
from database import SessionLocal, engine
from bigquery.cost_tracker import ensure_cost_table, record_query_cost

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

# Uniek per testrun zodat we onze eigen rijen kunnen herkennen en opruimen
TEST_MODULE = f"test_cost_{uuid.uuid4().hex[:8]}"
BYTES_SCANNED = 2_500_000_000_000  # 2.5 TB → $15.625 bij $6.25/TB


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


@pytest.fixture(scope="module")
def seeded_cost_row():
    """Schrijf één kostenrij in fact_bq_query_cost en ruim die na afloop op."""
    ensure_cost_table(engine)
    db = SessionLocal()
    try:
        record = record_query_cost(
            module=TEST_MODULE,
            query_label="regressietest kostentotalen",
            bytes_scanned=BYTES_SCANNED,
            duration_ms=1234,
            ok=True,
            db=db,
        )
        # De insert mag niet stil zijn mislukt
        row = db.execute(
            text("SELECT COUNT(*) FROM fact_bq_query_cost WHERE module = :m"),
            {"m": TEST_MODULE},
        ).scalar()
        assert row == 1, "kostenrij is niet opgeslagen"
        yield record
    finally:
        try:
            db.execute(
                text("DELETE FROM fact_bq_query_cost WHERE module = :m"),
                {"m": TEST_MODULE},
            )
            db.commit()
        finally:
            db.close()


def test_costs_endpoint_returns_nonzero_totals(client, admin_headers, seeded_cost_row):
    """GET /api/bigquery/costs geeft niet-nul totalen (USD + TB + by_module)."""
    resp = client.get("/api/bigquery/costs?days=7", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Het fail-safe pad zet een 'error'-sleutel — die mag hier niet voorkomen
    assert "error" not in data, f"kostensamenvatting viel terug op fail-safe: {data.get('error')}"

    assert data["total_bytes"] >= BYTES_SCANNED
    assert data["total_tb"] >= 2.5
    assert data["total_cost_usd"] >= 15.625 - 1e-6

    ours = [r for r in data["by_module"] if r["module"] == TEST_MODULE]
    assert len(ours) == 1, f"testmodule ontbreekt in by_module: {data['by_module']}"
    r = ours[0]
    assert r["query_count"] == 1
    assert r["total_bytes"] == BYTES_SCANNED
    assert r["total_tb"] == pytest.approx(2.5)
    assert r["total_cost_usd"] == pytest.approx(15.625, abs=1e-4)
    assert r["error_count"] == 0
    # Types moeten JSON-native zijn (geen Decimal-lek)
    assert isinstance(r["total_bytes"], int)
    assert isinstance(r["total_cost_usd"], float)


def test_scenarios_include_bigquery_costs(client, admin_headers, seeded_cost_row):
    """GET /api/platform/costs/scenarios telt de BigQuery-kosten mee."""
    resp = client.get("/api/platform/costs/scenarios?dagen=7", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    basis = data["gemeten_basis"]
    assert basis["bigquery_kosten_usd"] >= 15.625 - 1e-4
    assert basis["bigquery_tb_gescand"] >= 2.5
    assert basis["bigquery_queries"] >= 1
    assert basis["bigquery_kosten_eur_maand"] > 0

    # De BQ-kosten (per maand, in EUR) moeten in de variabele kosten zitten:
    # variabel per shop >= bq_kosten_eur_maand
    assert data["variabele_kosten_per_shop_eur_maand_expected"] >= basis["bigquery_kosten_eur_maand"]

    # En dus ook in elk scenario met 1 shop op EXPECTED niveau
    expected_1 = next(
        s for s in data["scenarios"] if s["shops"] == 1 and s["gebruiksniveau"] == "EXPECTED"
    )
    assert expected_1["variabele_kosten_eur_maand"] >= basis["bigquery_kosten_eur_maand"]
