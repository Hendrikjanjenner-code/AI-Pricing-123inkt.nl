"""
Tests voor node-specifieke concurrentscores per hiërarchie-node (taak #265).

- Scores verschillen aantoonbaar per node (zelfde concurrent, andere tak).
- Producten uit zustertakken beïnvloeden een node-score niet.
- Waarnemingen zonder interne mapping tellen niet mee en zijn zichtbaar
  als "mapping ontbreekt".
- API: /rankings en /competitors tonen node-specifieke scores bij een
  actieve hiërarchieselectie (incl. fallback van diepe nodes naar de
  dichtstbijzijnde gescoorde voorouder); zonder selectie blijft overall.
- De rankings-run (nachtrun/feed-refresh) werkt de node-scores mee bij.
"""
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from main import app
from database import SessionLocal
import models
from engine.competition_node_scores import run_competitor_node_scores

ADMIN_LOGIN = {"username": "dev_admin", "password": "admin123"}

PFX = f"NS{uuid.uuid4().hex[:6].upper()}"
COMP_A = f"{PFX}-alpha.nl"
COMP_B = f"{PFX}-beta.nl"


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
def seed(client):
    """Eigen test-shop: root → (Coffee, Tea), plus een diepe leaf onder Coffee
    en een SKU zonder hiërarchie-mapping."""
    db = SessionLocal()
    today = date.today()
    ids: dict = {}
    skus = {k: f"{PFX}-{k}" for k in ("C1", "C2", "T1", "T2", "U1")}
    try:
        shop = models.DimShop(shop_code=f"{PFX}-shop", name=f"{PFX} Shop", active=True)
        db.add(shop)
        db.flush()
        sid = shop.id

        db.add_all([
            models.DimProduct(sku_id=s, product_name=k, shop_id=sid,
                              current_price=10.0)
            for k, s in skus.items()
        ])
        db.flush()

        root = models.ProductHierarchyNode(name=f"{PFX}-Root", level=1)
        db.add(root); db.flush()
        root.path = f"/{root.id}/"
        coffee = models.ProductHierarchyNode(name=f"{PFX}-Coffee", level=2, parent_id=root.id)
        tea = models.ProductHierarchyNode(name=f"{PFX}-Tea", level=2, parent_id=root.id)
        db.add_all([coffee, tea]); db.flush()
        coffee.path = f"/{root.id}/{coffee.id}/"
        tea.path = f"/{root.id}/{tea.id}/"
        beans = models.ProductHierarchyNode(name=f"{PFX}-Beans", level=3, parent_id=coffee.id)
        db.add(beans); db.flush()
        beans.path = f"{coffee.path}{beans.id}/"

        db.add_all([
            # C1 hangt aan de diepe leaf; C2 direct aan Coffee.
            models.ProductHierarchyAssignment(sku_id=skus["C1"], node_id=beans.id, status="active"),
            models.ProductHierarchyAssignment(sku_id=skus["C2"], node_id=coffee.id, status="active"),
            models.ProductHierarchyAssignment(sku_id=skus["T1"], node_id=tea.id, status="active"),
            models.ProductHierarchyAssignment(sku_id=skus["T2"], node_id=tea.id, status="active"),
            # U1 heeft bewust GEEN mapping.
        ])

        # Waarnemingen: A sterk in Coffee (2/2), zwak in Tea (1/2), plus een
        # waarneming op de ongemapte SKU. B alleen in Tea.
        F = models.FactCompetitorPriceDaily
        db.add_all([
            F(date=today, sku_id=skus["C1"], shop_id=sid, competitor_name=COMP_A, price=9.5),
            F(date=today, sku_id=skus["C2"], shop_id=sid, competitor_name=COMP_A, price=10.5),
            F(date=today, sku_id=skus["T1"], shop_id=sid, competitor_name=COMP_A, price=14.0),
            F(date=today, sku_id=skus["U1"], shop_id=sid, competitor_name=COMP_A, price=8.0),
            F(date=today, sku_id=skus["T1"], shop_id=sid, competitor_name=COMP_B, price=10.2),
            F(date=today, sku_id=skus["T2"], shop_id=sid, competitor_name=COMP_B, price=9.8),
        ])

        # CIS: A hoog op Coffee-SKU's en dicht op onze prijs; laag/ver weg op Tea.
        C = models.CompetitorInfluenceScore
        db.add_all([
            C(sku_id=skus["C1"], competitor_name=COMP_A, run_date=today,
              cis_score=90.0, price_vs_own_pct=-5.0),
            C(sku_id=skus["C2"], competitor_name=COMP_A, run_date=today,
              cis_score=80.0, price_vs_own_pct=5.0),
            C(sku_id=skus["T1"], competitor_name=COMP_A, run_date=today,
              cis_score=20.0, price_vs_own_pct=40.0),
            C(sku_id=skus["T1"], competitor_name=COMP_B, run_date=today,
              cis_score=70.0, price_vs_own_pct=2.0),
            C(sku_id=skus["T2"], competitor_name=COMP_B, run_date=today,
              cis_score=60.0, price_vs_own_pct=-2.0),
        ])

        # Overall rankings + profielen (nodig voor /rankings en /competitors).
        for rank, name in ((1, COMP_A), (2, COMP_B)):
            db.add(models.CompetitorRanking(
                shop_id=sid, run_date=today, scope="overall",
                competitor_name=name, rank=rank, combined_score=1.0 / rank,
                competition_relevance_score=0.5, price_relevance_score=0.5,
                influence_score=0.5))
            db.add(models.CompetitorProfile(
                shop_id=sid, competitor_name=name, domain=name,
                functional_overlap_score=0.5, relevance_label="HIGH"))
        db.commit()
        ids = {"sid": sid, "root": root.id, "coffee": coffee.id,
               "tea": tea.id, "beans": beans.id, "skus": list(skus.values())}
        yield ids
    finally:
        db.rollback()
        sid = ids.get("sid")
        if sid is not None:
            for M, col in [
                (models.CompetitorHierarchyNodeScore, models.CompetitorHierarchyNodeScore.shop_id),
                (models.CompetitorRanking, models.CompetitorRanking.shop_id),
                (models.CompetitorProfile, models.CompetitorProfile.shop_id),
                (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.shop_id),
            ]:
                db.query(M).filter(col == sid).delete(synchronize_session=False)
            db.query(models.CompetitorInfluenceScore).filter(
                models.CompetitorInfluenceScore.sku_id.in_(ids["skus"])
            ).delete(synchronize_session=False)
            A = models.ProductHierarchyAssignment
            db.query(A).filter(A.sku_id.in_(ids["skus"])).delete(synchronize_session=False)
            N = models.ProductHierarchyNode
            for nid in (ids["beans"], ids["coffee"], ids["tea"], ids["root"]):
                db.query(N).filter(N.id == nid).delete(synchronize_session=False)
            db.query(models.CostUsageRecord).filter(
                models.CostUsageRecord.shop_id == sid).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_(ids["skus"])).delete(synchronize_session=False)
            db.query(models.DimShop).filter(models.DimShop.id == sid).delete(
                synchronize_session=False)
            db.commit()
        db.close()


@pytest.fixture(scope="module")
def node_run(seed):
    db = SessionLocal()
    try:
        written = run_competitor_node_scores(db, shop_id=seed["sid"])
        db.commit()
        yield written
    finally:
        db.close()


def _rows(db, sid, name=None, node_id="__any__"):
    S = models.CompetitorHierarchyNodeScore
    q = db.query(S).filter(S.shop_id == sid)
    if name:
        q = q.filter(S.competitor_name == name)
    if node_id != "__any__":
        q = q.filter(S.node_id == node_id) if node_id is not None \
            else q.filter(S.node_id.is_(None))
    return q.all()


def test_selected_node_preserves_unknown_scores_and_renormalizes(seed, node_run):
    """De hiërarchie-API mag ontbrekende node-input niet opnieuw als nul wegen."""
    from routes.competition import _node_scores_for_selection

    db = SessionLocal()
    try:
        row = db.query(models.CompetitorHierarchyNodeScore).filter(
            models.CompetitorHierarchyNodeScore.shop_id == seed["sid"],
            models.CompetitorHierarchyNodeScore.node_id == seed["coffee"],
            models.CompetitorHierarchyNodeScore.competitor_name == COMP_A,
        ).one()
        row.price_relevance_score = None
        row.influence_score = None
        row.combined_score = row.competition_relevance_score
        db.commit()

        by_comp, _, _ = _node_scores_for_selection(
            db, seed["sid"], str(seed["coffee"]))
        score = by_comp[COMP_A]
        assert score["price_relevance_score"] is None
        assert score["influence_score"] is None
        assert score["combined_score"] == score["competition_relevance_score"]
        assert score["evidence"]["combined_components"]["price_relevance"][
            "available"] is False
    finally:
        run_competitor_node_scores(db, shop_id=seed["sid"])
        db.commit()
        db.close()


def test_scores_verschillen_per_node(seed, node_run):
    db = SessionLocal()
    try:
        sid = seed["sid"]
        coffee = _rows(db, sid, COMP_A, seed["coffee"])
        tea = _rows(db, sid, COMP_A, seed["tea"])
        assert len(coffee) == 1 and len(tea) == 1
        c, t = coffee[0], tea[0]
        # Coffee: volledige dekking, hoge CIS, dicht op onze prijs.
        assert c.combined_score > t.combined_score
        assert c.competition_relevance_score > t.competition_relevance_score
        assert c.influence_score > t.influence_score
    finally:
        db.close()


def test_zustertak_beinvloedt_node_score_niet(seed, node_run):
    db = SessionLocal()
    try:
        sid = seed["sid"]
        # B is alleen in Tea waargenomen: geen Coffee-rij.
        assert _rows(db, sid, COMP_B, seed["coffee"]) == []
        # A's Coffee-noemer telt alleen Coffee-producten (2), geen thee.
        c = _rows(db, sid, COMP_A, seed["coffee"])[0]
        assert c.node_sku_count == 2 and c.observed_sku_count == 2
        # B's Tea-score: volledige tak-dekking.
        b = _rows(db, sid, COMP_B, seed["tea"])[0]
        assert b.node_sku_count == 2 and b.observed_sku_count == 2
        assert b.competition_relevance_score == 1.0
    finally:
        db.close()


def test_ongemapte_waarneming_zichtbaar_als_mapping_ontbreekt(seed, node_run):
    db = SessionLocal()
    try:
        rows = _rows(db, seed["sid"], COMP_A, None)
        assert len(rows) == 1
        assert rows[0].observation_count == 1
        assert rows[0].evidence.get("reason") == "mapping_ontbreekt"
        # De ongemapte waarneming telt nergens in een node-rij mee.
        for r in _rows(db, seed["sid"], COMP_A):
            if r.node_id is not None:
                assert r.observation_count <= 3
    finally:
        db.close()


def test_root_node_aggregeert_alle_descendants(seed, node_run):
    db = SessionLocal()
    try:
        r = _rows(db, seed["sid"], COMP_A, seed["root"])[0]
        assert r.node_sku_count == 4        # C1, C2, T1, T2 — niet U1
        assert r.observed_sku_count == 3    # C1, C2, T1
    finally:
        db.close()


def test_oude_cis_run_overschrijft_nieuwe_niet(seed, node_run):
    """Regressie: bij conflicterende CIS-historie telt per (concurrent, sku)
    deterministisch de meest recente run — een oude rij mag het dagsnapshot
    niet beïnvloeden, ongeacht rijvolgorde in de database."""
    from datetime import timedelta
    db = SessionLocal()
    try:
        sid = seed["sid"]
        sku_c1 = f"{PFX}-C1"
        # Voeg een OUDE, extreem afwijkende CIS-run toe voor A op C1.
        db.add(models.CompetitorInfluenceScore(
            sku_id=sku_c1, competitor_name=COMP_A,
            run_date=date.today() - timedelta(days=30),
            cis_score=1.0, price_vs_own_pct=99.0))
        db.commit()
        before = _rows(db, sid, COMP_A, seed["coffee"])[0]
        before_infl = before.influence_score
        run_competitor_node_scores(db, shop_id=sid)
        db.commit()
        after = _rows(db, sid, COMP_A, seed["coffee"])[0]
        # De oude run verandert niets: de recente CIS-waarden blijven gelden.
        assert after.influence_score == pytest.approx(before_infl)
    finally:
        db.rollback()
        db.query(models.CompetitorInfluenceScore).filter(
            models.CompetitorInfluenceScore.sku_id == f"{PFX}-C1",
            models.CompetitorInfluenceScore.cis_score == 1.0,
        ).delete(synchronize_session=False)
        # Herstel het snapshot voor volgende tests.
        run_competitor_node_scores(db, shop_id=seed["sid"])
        db.commit()
        db.close()


def test_rankings_run_werkt_node_scores_bij(seed, node_run):
    """De gedeelde rankings-run (nachtrun / feed-refresh) berekent de
    node-scores in dezelfde run mee."""
    from engine.competition_rankings import run_competitor_rankings
    db = SessionLocal()
    try:
        sid = seed["sid"]
        db.query(models.CompetitorHierarchyNodeScore).filter(
            models.CompetitorHierarchyNodeScore.shop_id == sid
        ).delete(synchronize_session=False)
        db.commit()
        run_competitor_rankings(db, shop_id=sid)
        assert len(_rows(db, sid)) > 0
    finally:
        db.close()


def test_api_rankings_node_specifiek(client, admin_headers, seed, node_run):
    r = client.get("/api/competition/rankings",
                   params={"shop_id": seed["sid"], "scope": "overall",
                           "hierarchy_node_ids": str(seed["coffee"])},
                   headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["score_basis"] == "hierarchy_nodes"
    assert body["unmapped_observations"] == 1
    names = {x["competitor_name"] for x in body["rankings"]}
    assert names == {COMP_A}
    row = body["rankings"][0]
    assert row["rank"] == 1 and row["trend"] is None
    # Node-score, niet de overall 0.5-waarden uit de seed.
    assert row["competition_relevance_score"] == 1.0
    assert row["evidence"]["score_basis"] == "hierarchy_nodes"


def test_api_rankings_diepe_node_valt_terug_op_voorouder(client, admin_headers, seed, node_run):
    r = client.get("/api/competition/rankings",
                   params={"shop_id": seed["sid"], "scope": "overall",
                           "hierarchy_node_ids": str(seed["beans"])},
                   headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["score_basis"] == "hierarchy_nodes"
    used = body["nodes_used"][0]
    assert used["selected_node_id"] == seed["beans"]
    assert used["scored_node_id"] == seed["coffee"]


def test_api_rankings_zonder_selectie_blijft_overall(client, admin_headers, seed, node_run):
    r = client.get("/api/competition/rankings",
                   params={"shop_id": seed["sid"], "scope": "overall"},
                   headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["score_basis"] == "overall"
    assert "nodes_used" not in body
    row = next(x for x in body["rankings"] if x["competitor_name"] == COMP_A)
    # Overall-rij, geen node-evidence.
    assert (row.get("evidence") or {}).get("score_basis") != "hierarchy_nodes"


def test_api_competitors_toont_node_scores(client, admin_headers, seed, node_run):
    r = client.get("/api/competition/competitors",
                   params={"shop_id": seed["sid"],
                           "hierarchy_node_ids": str(seed["tea"])},
                   headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["score_basis"] == "hierarchy_nodes"
    by_name = {i["competitor_name"]: i for i in body["items"]}
    assert by_name[COMP_B]["node_score"]["competition_relevance_score"] == 1.0
    assert by_name[COMP_A]["node_score"]["competition_relevance_score"] == 0.5
