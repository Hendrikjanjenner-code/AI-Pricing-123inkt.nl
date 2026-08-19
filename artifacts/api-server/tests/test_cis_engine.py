"""
Tests voor de CIS-engine (Competitor Influence Score) en de integratie
met de competitor rankings.

Verifieert:
1. run_cis_engine schrijft rijen naar competitor_influence_scores
2. Elke rij heeft een niet-nul cis_score
3. Na een rankings-run bevat de Influence-score in de rankings een niet-nul waarde
4. De ranking-explanation vermeldt hoeveel SKU-invloedscores zijn gebruikt (>0)
"""
import os
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from engine.competitor_influence import run_cis_engine, calculate_cis, get_cis_class, profile_baseline_influence
from engine.competition_rankings import run_competitor_rankings, W_INFLUENCE

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"CISTEST{uuid.uuid4().hex[:6]}"
SKU_A = f"{PFX}-A"
SKU_B = f"{PFX}-B"
COMP_1 = f"{PFX}-acme.nl"
COMP_2 = f"{PFX}-rival.nl"
CAT = f"{PFX}-cat"


# ── Fixtures ──────────────────────────────────────────────────────────────────

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
def seed_data():
    """
    Minimale seeddata in een geïsoleerde test-shop: 2 SKU's + 2 concurrenten
    met 20 dagen prijshistorie, een PCIS-score per SKU en een profiel voor COMP_1.

    Eigen shop zorgt ervoor dat run_cis_engine(sku_ids=...) gefocust kan worden
    op alleen deze SKU's, zodat tests snel blijven bij een volle DB.
    """
    db = SessionLocal()
    today = date.today()
    shop_id = None
    try:
        # Eigen test-shop aanmaken
        shop = models.DimShop(shop_code=f"{PFX}-cis-shop", name=f"{PFX} CIS Shop",
                               active=True)
        db.add(shop)
        db.flush()
        shop_id = shop.id

        # Producten (in eigen shop)
        db.add_all([
            models.DimProduct(
                sku_id=SKU_A, product_name="CIS Test Product A",
                category=CAT, current_price=25.0, cost_price=15.0,
                stock_quantity=100, shop_id=shop_id,
            ),
            models.DimProduct(
                sku_id=SKU_B, product_name="CIS Test Product B",
                category=CAT, current_price=10.0, cost_price=6.0,
                stock_quantity=50, shop_id=shop_id,
            ),
        ])
        db.flush()

        # Concurrentprijzen — 20 dagen voor beide SKU's, beide concurrenten
        price_rows = []
        for d_offset in range(20):
            d = today - timedelta(days=d_offset)
            for sku, base in [(SKU_A, 24.0), (SKU_B, 9.5)]:
                for comp, delta in [(COMP_1, 0.0), (COMP_2, 1.5)]:
                    price_rows.append(
                        models.FactCompetitorPriceDaily(
                            date=d, sku_id=sku,
                            competitor_name=comp,
                            price=base + delta,
                            source="test",
                            shop_id=shop_id,
                        )
                    )
        db.add_all(price_rows)

        # PCIS-scores (SkuCompetitionScore)
        db.add_all([
            models.SkuCompetitionScore(
                sku_id=SKU_A, run_date=today,
                competitor_relevance_score=0.8,
                product_comparability_score=0.75,
                price_sensitivity_score=0.7,
                substitution_score=0.3,
                competitor_price_reliability_score=0.8,
                basket_dependency_score=0.2,
                strategic_importance_score=0.6,
                pcis_score=0.72,
                competition_class="Strong",
            ),
            models.SkuCompetitionScore(
                sku_id=SKU_B, run_date=today,
                competitor_relevance_score=0.6,
                product_comparability_score=0.5,
                price_sensitivity_score=0.6,
                substitution_score=0.2,
                competitor_price_reliability_score=0.7,
                basket_dependency_score=0.1,
                strategic_importance_score=0.4,
                pcis_score=0.52,
                competition_class="Influence",
            ),
        ])

        # Concurrentprofiel voor COMP_1 (in eigen shop)
        db.add(models.CompetitorProfile(
            competitor_name=COMP_1,
            shop_id=shop_id,
            run_date=today,
            avg_delivery_days=2,
            in_stock_rate=0.92,
            functional_overlap_score=0.80,
            price_change_frequency=0.35,
            relevance_label="HIGH",
            traffic_light="green",
        ))

        db.commit()
        yield {"today": today, "shop_id": shop_id}
    finally:
        # Cleanup: shop-scoped rijen eerst, daarna SKU-scoped
        # Verwijder FK-afhankelijke PIM-tabellen vóór dim_product
        for pim_model, pim_col in [
            (models.PimAttributeValue, models.PimAttributeValue.sku_id),
        ]:
            db.query(pim_model).filter(
                pim_col.in_([SKU_A, SKU_B])
            ).delete(synchronize_session=False)

        for model, col in [
            (models.CompetitorInfluenceScore, models.CompetitorInfluenceScore.sku_id),
            (models.SkuCompetitionScore, models.SkuCompetitionScore.sku_id),
            (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.sku_id),
            (models.DimProduct, models.DimProduct.sku_id),
        ]:
            db.query(model).filter(
                col.in_([SKU_A, SKU_B])
            ).delete(synchronize_session=False)
        db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.competitor_name == COMP_1,
            models.CompetitorProfile.shop_id == shop_id,
        ).delete(synchronize_session=False)
        if shop_id is not None:
            for model, col in [
                (models.CompetitorRanking, models.CompetitorRanking.shop_id),
                (models.CompetitorInfluenceScore, models.CompetitorInfluenceScore.sku_id),
                (models.CostUsageRecord, models.CostUsageRecord.shop_id),
            ]:
                if col == models.CompetitorInfluenceScore.sku_id:
                    db.query(model).filter(
                        col.in_([SKU_A, SKU_B])
                    ).delete(synchronize_session=False)
                else:
                    db.query(model).filter(col == shop_id).delete(
                        synchronize_session=False)
            db.query(models.DimShop).filter(
                models.DimShop.id == shop_id,
            ).delete(synchronize_session=False)
        db.commit()
        db.close()


# ── Unit tests: pure formules ─────────────────────────────────────────────────

def test_calculate_cis_multiplicative():
    """CIS is het product van de vijf factoren, geclampd op 1.0."""
    score = calculate_cis(0.8, 0.75, 0.70, 0.9, 0.85)
    expected = round(min(0.8 * 0.75 * 0.70 * 0.9 * 0.85, 1.0), 4)
    assert score == expected
    assert 0.0 <= score <= 1.0


def test_calculate_cis_zero_factor():
    """Één factor 0 maakt CIS 0 (multiplicatief model)."""
    assert calculate_cis(0.8, 0.75, 0.0, 0.9, 0.85) == 0.0


def test_get_cis_class_thresholds():
    assert get_cis_class(0.85) == "Primaire concurrent"
    assert get_cis_class(0.65) == "Sterke concurrent"
    assert get_cis_class(0.50) == "Secundaire concurrent"
    assert get_cis_class(0.30) == "Zwakke concurrent"
    assert get_cis_class(0.10) == "Negeren"


# ── Integratie: run_cis_engine schrijft naar DB ───────────────────────────────

def test_run_cis_engine_writes_rows(seed_data):
    """run_cis_engine retourneert >0 en schrijft rijen voor de test-SKU's."""
    db = SessionLocal()
    try:
        # Scope tot test-SKU's: snel ongeacht hoeveel echte data in de DB staat
        written = run_cis_engine(db, ref_date=seed_data["today"],
                                 sku_ids=[SKU_A, SKU_B])
        assert written > 0, "Geen CIS-rijen geschreven terwijl prijsdata aanwezig is"

        rows = db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id.in_([SKU_A, SKU_B])
        ).all()
        assert len(rows) >= 2, f"Verwacht ≥2 CIS-rijen, kreeg {len(rows)}"
    finally:
        db.close()


def test_cis_scores_are_nonzero(seed_data):
    """Alle geschreven CIS-scores zijn strikt > 0."""
    db = SessionLocal()
    try:
        rows = db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id.in_([SKU_A, SKU_B]),
            models.CompetitorInfluenceScore.run_date == seed_data["today"],
        ).all()
        assert rows, "Geen CIS-rijen gevonden na engine-run"
        for row in rows:
            assert row.cis_score is not None, f"cis_score is None voor {row.sku_id}/{row.competitor_name}"
            assert row.cis_score > 0.0, (
                f"cis_score is 0 voor {row.sku_id}/{row.competitor_name} — "
                f"csrs={row.csrs_score}, css={row.css_score}"
            )
    finally:
        db.close()


def test_cis_sub_scores_populated(seed_data):
    """CSRS- en CSS-sub-scores zijn gevuld (niet allemaal 0)."""
    db = SessionLocal()
    try:
        row = db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id == SKU_A,
            models.CompetitorInfluenceScore.competitor_name == COMP_1,
            models.CompetitorInfluenceScore.run_date == seed_data["today"],
        ).first()
        assert row is not None, f"Geen CIS-rij voor {SKU_A}/{COMP_1}"
        assert row.availability_rate > 0.0, "availability_rate is 0"
        assert row.csrs_score > 0.0, "csrs_score is 0"
        assert row.css_score > 0.0, "css_score is 0"
        assert row.cis_class is not None, "cis_class is niet ingevuld"
        assert row.status in ("Actief", "Monitoren", "Negeren"), f"Onbekend status: {row.status}"
    finally:
        db.close()


def test_availability_rate_reflects_history(seed_data):
    """availability_rate ≈ 20/30 ≈ 0.67 (20 dagen data, venster 30 dagen)."""
    db = SessionLocal()
    try:
        row = db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id == SKU_A,
            models.CompetitorInfluenceScore.competitor_name == COMP_1,
            models.CompetitorInfluenceScore.run_date == seed_data["today"],
        ).first()
        assert row is not None
        # 20 dagen data uit een 30-daags venster ≈ 0.67
        assert 0.60 <= row.availability_rate <= 0.75, (
            f"availability_rate {row.availability_rate} buiten verwacht bereik"
        )
    finally:
        db.close()


def test_known_profile_raises_competitor_type_score(seed_data):
    """COMP_1 heeft een profiel → competitor_type_score hoger dan voor COMP_2."""
    db = SessionLocal()
    try:
        row1 = db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id == SKU_A,
            models.CompetitorInfluenceScore.competitor_name == COMP_1,
            models.CompetitorInfluenceScore.run_date == seed_data["today"],
        ).first()
        row2 = db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id == SKU_A,
            models.CompetitorInfluenceScore.competitor_name == COMP_2,
            models.CompetitorInfluenceScore.run_date == seed_data["today"],
        ).first()
        assert row1 and row2
        assert row1.competitor_type_score >= row2.competitor_type_score, (
            "Concurrent met profiel scoort niet hoger dan concurrent zonder profiel"
        )
    finally:
        db.close()


def test_idempotent_rerun(seed_data):
    """Een tweede engine-run vervangt de rijen (delete-then-insert, geen duplicaten)."""
    db = SessionLocal()
    try:
        run_cis_engine(db, ref_date=seed_data["today"], sku_ids=[SKU_A, SKU_B])
        count = db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id.in_([SKU_A, SKU_B]),
            models.CompetitorInfluenceScore.run_date == seed_data["today"],
        ).count()
        # Moet exact gelijk zijn (geen extra rijen door herrun)
        first_count = count
        run_cis_engine(db, ref_date=seed_data["today"], sku_ids=[SKU_A, SKU_B])
        count_after = db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id.in_([SKU_A, SKU_B]),
            models.CompetitorInfluenceScore.run_date == seed_data["today"],
        ).count()
        assert count_after == first_count, (
            f"Herrun produceerde {count_after} rijen, verwacht {first_count}"
        )
    finally:
        db.close()


# ── Regressie: Influence mag niet stilletjes terugvallen naar 0 ───────────────

def _overall_rankings(db, sid, run_date):
    return db.query(models.CompetitorRanking).filter(
        models.CompetitorRanking.shop_id == sid,
        models.CompetitorRanking.run_date == run_date,
        models.CompetitorRanking.scope == "overall",
    ).all()


def test_influence_nonzero_when_price_history_present(seed_data):
    """
    Vangnet voor de 30%-wegingsfactor: met prijshistorie én CIS-data mag de
    Influence-score in de rankings nooit terugvallen naar 0. Mislukt als een
    toekomstige wijziging in de rankings-engine of CIS-formule de score
    ongemerkt op 0 zet.
    """
    db = SessionLocal()
    sid = seed_data["shop_id"]
    today = seed_data["today"]
    try:
        # Volledige pipeline: CIS-engine gevolgd door rankings-engine
        written = run_cis_engine(db, ref_date=today, sku_ids=[SKU_A, SKU_B])
        assert written > 0, "CIS-engine schreef geen rijen ondanks prijshistorie"
        run_competitor_rankings(db, ref_date=today, shop_id=sid)

        rows = _overall_rankings(db, sid, today)
        assert rows, "Geen rankings geschreven voor de test-shop"
        nonzero = [r for r in rows if (r.influence_score or 0) > 0]
        assert nonzero, (
            "REGRESSIE: alle influence_scores zijn 0 terwijl prijshistorie en "
            "CIS-scores aanwezig zijn — de 30%-Influence-factor is uitgevallen. "
            f"Rijen: {[(r.competitor_name, r.influence_score) for r in rows]}"
        )
        for r in nonzero:
            assert r.evidence.get("cis_sku_count", 0) > 0
            assert abs(r.evidence.get("weights", {}).get("influence", 0) - W_INFLUENCE) < 1e-9
    finally:
        db.close()


def test_combined_score_differs_with_vs_without_cis(seed_data):
    """
    combined_score moet verschillen afhankelijk van CIS-aanwezigheid:
    zonder CIS-rijen valt Influence terug op 0 en daalt de combined_score
    met exact W_INFLUENCE * influence. Zou de score gelijk blijven, dan
    telt de Influence-factor niet meer mee (stille regressie).
    """
    db = SessionLocal()
    sid = seed_data["shop_id"]
    today = seed_data["today"]
    try:
        # Run MET CIS-data
        run_cis_engine(db, ref_date=today, sku_ids=[SKU_A, SKU_B])
        run_competitor_rankings(db, ref_date=today, shop_id=sid)
        with_cis = {r.competitor_name: (float(r.combined_score), float(r.influence_score))
                    for r in _overall_rankings(db, sid, today)}
        assert with_cis, "Geen rankings met CIS-data"
        assert any(infl > 0 for _, infl in with_cis.values()), (
            "Influence is al 0 mét CIS-data; regressietest kan verschil niet meten"
        )

        # Verwijder CIS-rijen en herrun rankings
        db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id.in_([SKU_A, SKU_B])
        ).delete(synchronize_session=False)
        db.commit()
        run_competitor_rankings(db, ref_date=today, shop_id=sid)
        without_cis = {r.competitor_name: (float(r.combined_score), float(r.influence_score))
                       for r in _overall_rankings(db, sid, today)}

        checked = 0
        for name, (comb_with, infl_with) in with_cis.items():
            if infl_with <= 0 or name not in without_cis:
                continue
            comb_without, infl_without = without_cis[name]
            # Zonder CIS-rijen valt Influence terug op de profiel-baseline
            # (of 0 zonder profiel) — nooit stilletjes op de oude waarde.
            prof = db.query(models.CompetitorProfile).filter(
                models.CompetitorProfile.shop_id == sid,
                models.CompetitorProfile.competitor_name == name,
            ).first()
            expected_infl = profile_baseline_influence(prof) if prof else 0.0
            assert abs(infl_without - expected_infl) < 0.001, (
                f"Influence van {name} is {infl_without} zonder CIS-rijen; "
                f"verwacht profiel-baseline {expected_infl}"
            )
            # De Influence-factor moet aantoonbaar meetellen: het verschil in
            # combined_score is exact W_INFLUENCE * (influence-verschil).
            expected_delta = W_INFLUENCE * (infl_with - infl_without)
            assert abs((comb_with - comb_without) - expected_delta) < 0.001, (
                f"combined_score-verschil {comb_with - comb_without:.4f} wijkt af van "
                f"W_INFLUENCE*Δinfluence = {expected_delta:.4f} voor {name} — "
                f"de Influence-factor telt niet (correct) meer mee"
            )
            checked += 1
        assert checked > 0, "Geen enkele concurrent gecontroleerd; regressietest meet niets"
    finally:
        # Herstel CIS-data voor volgende tests in de module
        try:
            run_cis_engine(db, ref_date=today, sku_ids=[SKU_A, SKU_B])
        finally:
            db.close()


# ── Integratie: rankings/run-endpoint vult Influence-score ────────────────────

def test_rankings_run_returns_cis_count(client, admin_headers, seed_data):
    """POST /api/competition/rankings/run retourneert cis_scores_geschreven > 0."""
    sid = seed_data["shop_id"]
    resp = client.post("/api/competition/rankings/run", headers=admin_headers,
                       json={"shop_id": sid})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "cis_scores_geschreven" in body, "Ontbrekend veld cis_scores_geschreven"
    assert body["cis_scores_geschreven"] > 0, (
        f"cis_scores_geschreven is {body['cis_scores_geschreven']} — CIS-engine draait niet"
    )
    assert body["rankings_geschreven"] >= 0


def test_rankings_influence_score_nonzero_after_run(client, admin_headers, seed_data):
    """
    Na een rankings/run bevat minstens één ranking een niet-nul influence_score,
    en de explanation vermeldt het aantal SKU-invloedscores.
    """
    sid = seed_data["shop_id"]
    # Trigger de run — scope tot de test-shop (snel + bevat onze CIS-data)
    resp = client.post("/api/competition/rankings/run", headers=admin_headers,
                       json={"shop_id": sid})
    assert resp.status_code == 200, resp.text

    # Lees de rankings op voor dezelfde test-shop
    resp = client.get(f"/api/competition/rankings?scope=overall&shop_id={sid}",
                      headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rankings = body.get("rankings", [])

    if not rankings:
        pytest.skip("Geen rankings beschikbaar (onvoldoende profieldata in testomgeving)")

    # Minstens één ranking met influence_score > 0
    nonzero_influence = [r for r in rankings if r.get("influence_score", 0) > 0]
    assert nonzero_influence, (
        "Alle influence_scores zijn 0 na rankings/run — CIS-scores worden niet meegenomen. "
        f"Rankings: {rankings}"
    )

    # Explanation vermeldt het aantal SKU-invloedscores (> 0 voor minstens één)
    # — behalve voor concurrenten met een profiel-baseline (geen prijshistorie).
    for r in nonzero_influence:
        evidence = r.get("evidence", {})
        if evidence.get("influence_basis") == "profiel":
            continue
        explanation = r.get("explanation", "")
        assert "SKU-invloedscores" in explanation, (
            f"Explanation vermeldt SKU-invloedscores niet: {explanation!r}"
        )
        assert evidence.get("cis_sku_count", 0) > 0, (
            f"evidence.cis_sku_count is 0 voor {r['competitor_name']}"
        )


# ── Profiel-baseline: concurrent zonder prijshistorie ─────────────────────────

def test_profile_baseline_influence_formula():
    """Baseline uit profiel alleen: overlap, relevance_label en in_stock_rate."""
    from engine.competitor_influence import profile_baseline_influence

    class _P:
        functional_overlap_score = 0.8
        relevance_label = "HIGH"
        in_stock_rate = 0.9

    score = profile_baseline_influence(_P())
    expected = round(0.5 * 0.8 + 0.3 * 0.9 + 0.2 * 0.9, 4)
    assert score == expected
    assert score > 0.0

    class _Empty:
        functional_overlap_score = None
        relevance_label = None
        in_stock_rate = None

    # Zelfs een leeg profiel geeft een niet-nul baseline (labelscore 0.5 default)
    assert profile_baseline_influence(_Empty()) > 0.0


def test_rankings_profile_only_competitor_gets_baseline_influence(seed_data):
    """
    Een concurrent met alleen een profiel (geen prijshistorie) krijgt een
    niet-nul influence_score op basis van het profiel, en de explanation en
    evidence maken het onderscheid ('profiel' vs 'prijshistorie') expliciet.
    """
    from engine.competition_rankings import run_competitor_rankings

    comp_new = f"{PFX}-nieuw.nl"
    sid = seed_data["shop_id"]
    db = SessionLocal()
    try:
        db.add(models.CompetitorProfile(
            competitor_name=comp_new,
            shop_id=sid,
            run_date=seed_data["today"],
            functional_overlap_score=0.7,
            relevance_label="MONITOR",
            in_stock_rate=0.85,
        ))
        db.commit()

        # Zorg dat er CIS-rijen zijn voor de concurrenten mét prijshistorie
        run_cis_engine(db, ref_date=seed_data["today"], sku_ids=[SKU_A, SKU_B])
        run_competitor_rankings(db, ref_date=seed_data["today"], shop_id=sid)

        rows = db.query(models.CompetitorRanking).filter(
            models.CompetitorRanking.shop_id == sid,
            models.CompetitorRanking.run_date == seed_data["today"],
            models.CompetitorRanking.scope == "overall",
        ).all()
        by_name = {r.competitor_name: r for r in rows}

        # Profiel-only concurrent: niet-nul influence, basis = profiel
        assert comp_new in by_name, f"{comp_new} ontbreekt in rankings: {list(by_name)}"
        r_new = by_name[comp_new]
        assert (r_new.influence_score or 0) > 0.0, (
            "Influence-score blijft 0 voor concurrent zonder prijshistorie"
        )
        assert (r_new.evidence or {}).get("influence_basis") == "profiel"
        assert "profiel" in (r_new.explanation or ""), r_new.explanation
        assert "prijshistorie" in (r_new.explanation or ""), r_new.explanation

        # Concurrent mét prijshistorie: basis = prijshistorie
        assert COMP_1 in by_name
        r_hist = by_name[COMP_1]
        assert (r_hist.evidence or {}).get("influence_basis") == "prijshistorie"
        assert "prijshistorie" in (r_hist.explanation or "")
    finally:
        db.query(models.CompetitorProfile).filter(
            models.CompetitorProfile.competitor_name == comp_new,
            models.CompetitorProfile.shop_id == sid,
        ).delete(synchronize_session=False)
        db.commit()
        db.close()
