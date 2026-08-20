"""
Automatische producthiërarchie uit feed-categorieën (taak #274).

Dekt:
- leeg → opgebouwd: categorie/subcategorie uit dim_product wordt een
  twee-laags boom met padtabel en actieve toewijzingen;
- idempotent + incrementeel: her-run zonder wijzigingen doet niets,
  een nieuwe categorie uit een latere sync komt erbij;
- verplaatsing: categorie-wijziging superseded de oude toewijzing
  (niet-destructief);
- handmatige boom is leidend: autobuild doet niets zodra er een
  niet-auto-node bestaat, en een import-apply zet de auto-boom buiten
  gebruik (retire);
- de productenlijst-API filtert op hierarchy_node_ids (subtree-expansie).
"""
import pytest
from fastapi.testclient import TestClient

import models
from main import app
from database import SessionLocal
from services.hierarchy_autobuild import (
    AUTO_SOURCE, autobuild_hierarchy, retire_auto_hierarchy,
)

PFX = "hatest"
CAT1 = f"{PFX.title()} Printers"
SUB1 = f"{PFX.title()} Laser"
CAT2 = f"{PFX.title()} Papier"
SKU1 = f"{PFX}-sku-1"
SKU2 = f"{PFX}-sku-2"
SKU3 = f"{PFX}-sku-3"


def _cleanup(db):
    node_ids = [n.id for n in db.query(models.ProductHierarchyNode)
                .filter(models.ProductHierarchyNode.name.like(f"{PFX.title()}%")).all()]
    if node_ids:
        db.query(models.ProductHierarchyAssignment).filter(
            models.ProductHierarchyAssignment.node_id.in_(node_ids)
        ).delete(synchronize_session=False)
        db.query(models.ProductHierarchyPath).filter(
            models.ProductHierarchyPath.leaf_node_id.in_(node_ids)
        ).delete(synchronize_session=False)
        db.query(models.ProductHierarchyNode).filter(
            models.ProductHierarchyNode.id.in_(node_ids)
        ).delete(synchronize_session=False)
    db.query(models.ProductHierarchyAssignment).filter(
        models.ProductHierarchyAssignment.sku_id.like(f"{PFX}%")
    ).delete(synchronize_session=False)
    db.query(models.DimProduct).filter(
        models.DimProduct.sku_id.like(f"{PFX}%")
    ).delete(synchronize_session=False)
    db.commit()


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    _cleanup(session)
    yield session
    _cleanup(session)
    session.close()


@pytest.fixture(scope="module")
def producten(db):
    db.add_all([
        models.DimProduct(sku_id=SKU1, product_name="Hatest Laserprinter",
                          category=CAT1, subcategory=SUB1,
                          is_active=True, shop_id=1),
        models.DimProduct(sku_id=SKU2, product_name="Hatest A4 Papier",
                          category=CAT2, subcategory=None,
                          is_active=True, shop_id=1),
    ])
    db.commit()
    return [SKU1, SKU2]


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
    resp = client.post("/api/auth/login",
                       json={"username": "dev_admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _node(db, name, parent_id=None):
    q = db.query(models.ProductHierarchyNode).filter(
        models.ProductHierarchyNode.name == name)
    if parent_id is not None:
        q = q.filter(models.ProductHierarchyNode.parent_id == parent_id)
    return q.first()


def _active_assignment(db, sku_id):
    return (db.query(models.ProductHierarchyAssignment)
            .filter(models.ProductHierarchyAssignment.sku_id == sku_id,
                    models.ProductHierarchyAssignment.status == "active")
            .first())


def test_leeg_naar_opgebouwd(db, producten):
    report = autobuild_hierarchy(db)
    assert report["skipped"] is False

    cat1 = _node(db, CAT1)
    assert cat1 is not None and cat1.source == AUTO_SOURCE
    assert cat1.level == 1 and cat1.path and cat1.is_active

    sub1 = _node(db, SUB1, parent_id=cat1.id)
    assert sub1 is not None and sub1.level == 2
    assert sub1.path.startswith(cat1.path.rstrip("/") + "/") or \
        sub1.path.startswith(cat1.path)
    assert CAT1 in (sub1.path_names or "")

    # Padtabel gesynct: subcategorie is blad, categorie-met-kind niet.
    leaf_ids = {p.leaf_node_id for p in db.query(models.ProductHierarchyPath).all()}
    assert sub1.id in leaf_ids
    assert cat1.id not in leaf_ids

    # Toewijzingen naar de diepste node.
    a1 = _active_assignment(db, SKU1)
    assert a1 is not None and a1.node_id == sub1.id and a1.source == AUTO_SOURCE
    cat2 = _node(db, CAT2)
    a2 = _active_assignment(db, SKU2)
    assert a2 is not None and a2.node_id == cat2.id


def test_idempotent_en_incrementeel(db, producten):
    before = db.query(models.ProductHierarchyNode).count()
    report = autobuild_hierarchy(db)
    assert report["skipped"] is False
    assert report["nodes_created"] == 0
    assert report["assignments_written"] == 0
    assert db.query(models.ProductHierarchyNode).count() == before

    # Nieuwe categorie uit een latere sync komt erbij.
    cat3 = f"{PFX.title()} Toners"
    db.add(models.DimProduct(sku_id=SKU3, product_name="Hatest Toner",
                             category=cat3, subcategory=None,
                             is_active=True, shop_id=1))
    db.commit()
    autobuild_hierarchy(db)
    n3 = _node(db, cat3)
    assert n3 is not None and n3.source == AUTO_SOURCE
    a3 = _active_assignment(db, SKU3)
    assert a3 is not None and a3.node_id == n3.id


def test_verplaatsing_superseded_niet_destructief(db, producten):
    # SKU3 verhuist naar een andere categorie.
    p = db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == SKU3).first()
    p.category = CAT2
    p.subcategory = None
    db.commit()
    autobuild_hierarchy(db)

    cat2 = _node(db, CAT2)
    a = _active_assignment(db, SKU3)
    assert a is not None and a.node_id == cat2.id
    oud = (db.query(models.ProductHierarchyAssignment)
           .filter(models.ProductHierarchyAssignment.sku_id == SKU3,
                   models.ProductHierarchyAssignment.status == "superseded")
           .all())
    assert len(oud) >= 1  # oude rij blijft bestaan
    assert all(r.valid_to is not None for r in oud)


def test_products_api_filtert_op_hierarchy_node(db, producten, client, admin_headers):
    cat1 = _node(db, CAT1)
    resp = client.get("/api/products",
                      params={"hierarchy_node_ids": str(cat1.id),
                              "page_size": 200},
                      headers=admin_headers)
    assert resp.status_code == 200, resp.text
    skus = {it["sku_id"] for it in resp.json()["items"]}
    # Subtree-expansie: SKU1 hangt aan de subcategorie onder CAT1.
    assert SKU1 in skus
    assert SKU2 not in skus

    # Niet-bestaande node: filter actief, niets matcht (lege selectie ≠ geen filter).
    resp2 = client.get("/api/products",
                       params={"hierarchy_node_ids": "999999999"},
                       headers=admin_headers)
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 0


def test_handmatige_boom_is_leidend(db, producten):
    handmatig = models.ProductHierarchyNode(
        name=f"{PFX.title()} Handmatig", level=1, is_active=True,
        source="handmatig", created_by="test")
    db.add(handmatig)
    db.commit()
    try:
        report = autobuild_hierarchy(db)
        assert report["skipped"] is True
    finally:
        db.delete(handmatig)
        db.commit()


def test_import_hergebruikt_auto_nodes_nooit(db, producten):
    """Regressie: de import-index mag geretireerde auto-nodes (zelfde naam)
    nooit hergebruiken — anders wordt de boom deels 'auto' en verliest de
    import zijn leidende rol."""
    from services.product_hierarchy import _existing_tree_index
    by_id, by_parent_name, by_opt = _existing_tree_index(db)
    auto_ids = {n.id for n in db.query(models.ProductHierarchyNode).filter(
        models.ProductHierarchyNode.source == AUTO_SOURCE).all()}
    assert auto_ids, "voorwaarde: er bestaan auto-nodes"
    assert not (set(by_id) & auto_ids)
    assert all(n.id not in auto_ids for n in by_parent_name.values())

    # En na een import (gesimuleerd met een actieve import-node met dezelfde
    # naam als een auto-categorie) blijft autobuild uit — geen dubbele actieve
    # toewijzingen naast de import.
    retired = retire_auto_hierarchy(db)
    db.commit()
    assert retired >= 1
    imp = models.ProductHierarchyNode(
        name=CAT1, level=1, is_active=True, source="import",
        created_by="test")
    db.add(imp)
    db.commit()
    try:
        report = autobuild_hierarchy(db)
        assert report["skipped"] is True
        assert (db.query(models.ProductHierarchyNode)
                .filter(models.ProductHierarchyNode.source == AUTO_SOURCE,
                        models.ProductHierarchyNode.is_active.is_(True))
                .count()) == 0
        assert _active_assignment(db, SKU1) is None
    finally:
        db.delete(imp)
        db.commit()
    # Herstel de auto-boom voor de volgende test.
    autobuild_hierarchy(db)


def test_retire_bij_import_apply(db, producten):
    # Retire zet de auto-boom buiten gebruik (import wordt leidend) ...
    retired = retire_auto_hierarchy(db)
    db.commit()
    assert retired >= 3
    actief = (db.query(models.ProductHierarchyNode)
              .filter(models.ProductHierarchyNode.source == AUTO_SOURCE,
                      models.ProductHierarchyNode.is_active.is_(True)).count())
    assert actief == 0
    assert _active_assignment(db, SKU1) is None

    # ... en niets is verwijderd (niet-destructief).
    assert _node(db, CAT1) is not None

    # Herstel: zonder handmatige boom bouwt de volgende sync hem gewoon weer op
    # (reactivatie van bestaande nodes, geen duplicaten).
    before = db.query(models.ProductHierarchyNode).filter(
        models.ProductHierarchyNode.name.like(f"{PFX.title()}%")).count()
    autobuild_hierarchy(db)
    after = db.query(models.ProductHierarchyNode).filter(
        models.ProductHierarchyNode.name.like(f"{PFX.title()}%")).count()
    assert after == before
    cat1 = _node(db, CAT1)
    assert cat1.is_active
    assert _active_assignment(db, SKU1) is not None


def test_verdwenen_categorie_en_inactief_product(db, producten, client, admin_headers):
    """Feed volgt: product inactief → toewijzing superseded; categorie zonder
    producten meer → node gedeactiveerd en niet meer filterbaar."""
    # SKU3 (enige product in CAT2 naast SKU2)... maak SKU2 inactief en geef
    # SKU3 zijn oude categorie terug zodat CAT2 leeg raakt is te complex;
    # simpeler: maak SKU3 inactief (enige in CAT2 samen met SKU2) en
    # verwijder de categorie van SKU2.
    p2 = db.query(models.DimProduct).filter(models.DimProduct.sku_id == SKU2).first()
    p3 = db.query(models.DimProduct).filter(models.DimProduct.sku_id == SKU3).first()
    p3.is_active = False
    p2.category = None
    db.commit()

    report = autobuild_hierarchy(db)
    assert report["assignments_retired"] >= 2
    assert _active_assignment(db, SKU2) is None
    assert _active_assignment(db, SKU3) is None

    cat2 = _node(db, CAT2)
    assert cat2 is not None and cat2.is_active is False  # gedeactiveerd, niet verwijderd

    # API: filter op de verdwenen categorie matcht niets meer.
    resp = client.get("/api/products",
                      params={"hierarchy_node_ids": str(cat2.id)},
                      headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Herstel + her-run: categorie en toewijzing komen terug (reactivatie).
    p2.category = CAT2
    p3.is_active = True
    db.commit()
    autobuild_hierarchy(db)
    db.refresh(cat2)
    assert cat2.is_active
    assert _active_assignment(db, SKU2) is not None


def test_concurrency_lock_skipt_tweede_autobuild(db, producten):
    """Regressie: een tweede autobuild (of een import-apply, die dezelfde
    lock blokkerend neemt) kan nooit gelijktijdig muteren."""
    if db.bind.dialect.name != "postgresql":
        pytest.skip("advisory locks zijn Postgres-only")
    from sqlalchemy import text
    from services.hierarchy_autobuild import _ADVISORY_LOCK_KEY
    holder = SessionLocal()
    try:
        got = holder.execute(text("SELECT pg_try_advisory_xact_lock(:k)"),
                             {"k": _ADVISORY_LOCK_KEY}).scalar()
        assert got is True
        report = autobuild_hierarchy(db)
        assert report["skipped"] is True
        assert "bezig" in report["reason"]
    finally:
        holder.rollback()
        holder.close()
    # Na vrijgave werkt het weer.
    assert autobuild_hierarchy(db)["skipped"] is False
