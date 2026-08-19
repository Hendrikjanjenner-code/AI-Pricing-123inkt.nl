"""Tests voor de globale filtercontext (taak #216): server-side
descendant-expansie en merkfilter (routes/global_filters.py)."""
import uuid

import pytest

import models
from database import SessionLocal
from routes.global_filters import parse_csv, parse_csv_ints, resolve_sku_filter

PFX = f"GFT{uuid.uuid4().hex[:6].upper()}"


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def hierarchy_data(db):
    """Parent → child hiërarchie met elk één actief toegewezen product."""
    skus = [f"{PFX}-A", f"{PFX}-B", f"{PFX}-C"]
    db.add_all([
        models.DimProduct(sku_id=skus[0], product_name="GF parent prod", brand=f"{PFX}-MerkX"),
        models.DimProduct(sku_id=skus[1], product_name="GF child prod", brand=f"{PFX}-MerkY"),
        models.DimProduct(sku_id=skus[2], product_name="GF los prod", brand=f"{PFX}-MerkY"),
    ])
    db.flush()
    parent = models.ProductHierarchyNode(name=f"{PFX}-Parent", level=1, path_names=f"{PFX}-Parent")
    db.add(parent); db.flush()
    parent.path = f"/{parent.id}/"
    child = models.ProductHierarchyNode(name=f"{PFX}-Child", level=2,
                                        parent_id=parent.id, path_names=f"{PFX}-Parent > {PFX}-Child")
    db.add(child); db.flush()
    child.path = f"/{parent.id}/{child.id}/"
    other = models.ProductHierarchyNode(name=f"{PFX}-Other", level=1, path_names=f"{PFX}-Other")
    db.add(other); db.flush()
    other.path = f"/{other.id}/"
    db.add_all([
        models.ProductHierarchyAssignment(sku_id=skus[0], node_id=parent.id, status="active"),
        models.ProductHierarchyAssignment(sku_id=skus[1], node_id=child.id, status="active"),
        models.ProductHierarchyAssignment(sku_id=skus[2], node_id=other.id, status="active"),
    ])
    db.commit()
    yield {"skus": skus, "parent": parent.id, "child": child.id, "other": other.id}
    A, N, P = (models.ProductHierarchyAssignment, models.ProductHierarchyNode, models.DimProduct)
    db.rollback()
    db.query(A).filter(A.sku_id.in_(skus)).delete(synchronize_session=False)
    for nid in (child.id, parent.id, other.id):
        db.query(N).filter(N.id == nid).delete(synchronize_session=False)
    db.query(P).filter(P.sku_id.in_(skus)).delete(synchronize_session=False)
    db.commit()


def test_parse_helpers():
    assert parse_csv_ints("1, 2,x,3") == [1, 2, 3]
    assert parse_csv_ints(None) == []
    assert parse_csv(" a , ,b") == ["a", "b"]


def test_geen_filter_geeft_none(db):
    assert resolve_sku_filter(db, None, None) is None
    assert resolve_sku_filter(db, "", "") is None


def test_parent_selectie_telt_descendants_mee(db, hierarchy_data):
    d = hierarchy_data
    result = resolve_sku_filter(db, str(d["parent"]), None)
    # Parent-node zelf én de child-node (descendant) — niet de losse tak.
    assert result == {d["skus"][0], d["skus"][1]}


def test_child_selectie_blijft_beperkt(db, hierarchy_data):
    d = hierarchy_data
    assert resolve_sku_filter(db, str(d["child"]), None) == {d["skus"][1]}


def test_merkfilter_en_combinatie(db, hierarchy_data):
    d = hierarchy_data
    merk = f"{PFX}-MerkY"
    alleen_merk = resolve_sku_filter(db, None, merk)
    assert alleen_merk == {d["skus"][1], d["skus"][2]}
    # Combinatie: doorsnede van hiërarchie (parent-subtree) en merk.
    combi = resolve_sku_filter(db, str(d["parent"]), merk)
    assert combi == {d["skus"][1]}


def test_onbekende_node_matcht_niets(db):
    assert resolve_sku_filter(db, "-12345", None) == set()
