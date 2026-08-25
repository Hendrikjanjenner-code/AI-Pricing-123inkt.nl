"""Tests voor de canonieke producthiërarchie (taak #215)."""
import io
import uuid

import pytest
from fastapi.testclient import TestClient

import models
from database import SessionLocal
from main import app

PFX = f"PHT{uuid.uuid4().hex[:6].upper()}"  # unieke prefix per testrun


@pytest.fixture(scope="module")
def client(hierarchy_suite_lock):
    c = TestClient(app)
    c.__enter__()
    yield c
    try:
        c.__exit__(None, None, None)
    except Exception:
        pass


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin_headers(client):
    return _login(client, "admin", "admin123")


@pytest.fixture(scope="module")
def viewer_headers(client):
    return _login(client, "viewer", "viewer123")


def _csv(rows: list[str]) -> bytes:
    return ("optionId,productCode,path\n" + "\n".join(rows)).encode()


def _upload(client, headers, content: bytes, name=None):
    # Unieke bestandsnaam per testrun: zo is testresidu herkenbaar én kan de
    # teardown de ImportJob-rijen gericht verwijderen. Test-importjobs die
    # achterblijven met status "geimporteerd" worden anders de "laatst
    # toegepaste import" voor auto_assign_new_products, waardoor echte
    # feed-producten nooit meer automatisch worden toegewezen.
    name = name or f"{PFX}-hier.csv"
    r = client.post(
        "/api/product-hierarchy/import/upload",
        headers=headers,
        files={"file": (name, io.BytesIO(content), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def ph_products():
    """Twee eigen testproducten; volledige teardown van alle PH-testdata."""
    db = SessionLocal()
    skus = [f"{PFX}-SKU-1", f"{PFX}-SKU-2"]
    for s in skus:
        db.add(models.DimProduct(sku_id=s, product_name=f"PH test {s}"))
    db.commit()
    yield skus
    # teardown: alles wat met deze prefix te maken heeft
    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    P = models.ProductHierarchyPath
    S = models.ProductHierarchyStagingRow
    C = models.ProductHierarchyChangeLog
    db.rollback()
    node_ids = [nid for (nid,) in db.query(N.id).filter(N.path_names.like(f"%{PFX}%"))]
    if node_ids:
        db.query(A).filter(A.node_id.in_(node_ids)).delete(synchronize_session=False)
        db.query(P).filter(P.leaf_node_id.in_(node_ids)).delete(synchronize_session=False)
        db.query(C).filter(C.node_id.in_(node_ids)).delete(synchronize_session=False)
    db.query(A).filter(A.sku_id.in_(skus)).delete(synchronize_session=False)
    db.query(C).filter(C.sku_id.in_(skus)).delete(synchronize_session=False)
    db.query(S).filter(S.product_code.in_(skus)).delete(synchronize_session=False)
    # ImportJob-residu opruimen: test-jobs mogen nooit als "laatst toegepaste
    # import" achterblijven (zie _upload). Eerst alle verwijzingen lossnijden
    # (retire_auto_hierarchy stempelt superseded rijen met het job-id).
    J = models.ImportJob
    job_ids = [j for (j,) in db.query(J.id).filter(
        J.upload_type == "product_hierarchy",
        J.filename.like(f"{PFX}%"))]
    if job_ids:
        db.query(A).filter(A.import_job_id.in_(job_ids)).update(
            {A.import_job_id: None}, synchronize_session=False)
        db.query(C).filter(C.import_job_id.in_(job_ids)).delete(
            synchronize_session=False)
        db.query(S).filter(S.job_id.in_(job_ids)).delete(
            synchronize_session=False)
        db.query(J).filter(J.id.in_(job_ids)).delete(synchronize_session=False)
    # diepste nodes eerst verwijderen i.v.m. self-FK
    if node_ids:
        for n in sorted(db.query(N).filter(N.id.in_(node_ids)),
                        key=lambda x: -(x.level or 0)):
            db.delete(n)
    db.commit()
    db.query(models.DimProduct).filter(
        models.DimProduct.sku_id.in_(skus)).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_volledige_import_flow(client, admin_headers, ph_products):
    sku1, sku2 = ph_products
    content = _csv([
        f"{PFX}-O1,{sku1},{PFX}-Kantoor > {PFX}-Papier > {PFX}-A4",
        f"{PFX}-O2,{sku2},{PFX}-Kantoor > {PFX}-Papier > {PFX}-A3",
        f"{PFX}-O3,{PFX}-ONBEKEND,{PFX}-Kantoor > {PFX}-Pennen > {PFX}-Markers",
        f"{PFX}-O1,{sku1},{PFX}-Kantoor > {PFX}-Papier > {PFX}-A4",  # duplicaat
    ])
    up = _upload(client, admin_headers, content)
    job_id = up["job_id"]
    assert up["rows_staged"] == 4
    assert up["mapping"]["option_col"] == "optionid"
    assert up["mapping"]["path_col"] == "path"

    # impact vóór validatie moet 409 geven
    r = client.get(f"/api/product-hierarchy/import/{job_id}/impact", headers=admin_headers)
    assert r.status_code == 409

    val = client.post(f"/api/product-hierarchy/import/{job_id}/validate",
                      headers=admin_headers).json()
    assert val["counts"]["geldig"] == 3
    assert val["counts"]["duplicaten"] == 1
    assert val["counts"]["gekoppeld"] == 2
    assert val["counts"]["niet_gevonden"] == 1

    imp = client.get(f"/api/product-hierarchy/import/{job_id}/impact",
                     headers=admin_headers).json()
    assert imp["nodes"]["nieuw"] == 6  # 1 root, 2 tussen, 3 leaves
    assert imp["assignments"]["nieuw"] == 2
    assert imp["niet_destructief"] is True

    res = client.post(f"/api/product-hierarchy/import/{job_id}/apply",
                      headers=admin_headers).json()
    assert res["stats"]["nodes_nieuw"] == 6
    assert res["stats"]["assignments_nieuw"] == 2

    # nogmaals toepassen → 409
    r = client.post(f"/api/product-hierarchy/import/{job_id}/apply", headers=admin_headers)
    assert r.status_code == 409

    # zoeken + breadcrumb + descendants
    hits = client.get(f"/api/product-hierarchy/search?q={PFX}-A4",
                      headers=admin_headers).json()
    assert len(hits) == 1
    leaf = hits[0]
    assert leaf["external_option_id"] == f"{PFX}-O1"
    bc = client.get(f"/api/product-hierarchy/nodes/{leaf['id']}/breadcrumb",
                    headers=admin_headers).json()["breadcrumb"]
    assert [b["name"] for b in bc] == [f"{PFX}-Kantoor", f"{PFX}-Papier", f"{PFX}-A4"]

    root = bc[0]
    desc = client.get(f"/api/product-hierarchy/nodes/{root['id']}/descendants",
                      headers=admin_headers).json()
    assert desc["totaal"] == 5

    prods = client.get(
        f"/api/product-hierarchy/nodes/{root['id']}/products?include_descendants=true",
        headers=admin_headers).json()
    assert prods["totaal"] == 2
    assert {p["sku_id"] for p in prods["producten"]} == {sku1, sku2}

    # tweede import: rename + verplaatsing (niet-destructief)
    content2 = _csv([
        f"{PFX}-O2,{sku2},{PFX}-Kantoor > {PFX}-Papier > {PFX}-A3-Groot",
        f"{PFX}-O3,{sku1},{PFX}-Kantoor > {PFX}-Papier > {PFX}-Markers",
    ])
    up2 = _upload(client, admin_headers, content2)
    client.post(f"/api/product-hierarchy/import/{up2['job_id']}/validate",
                headers=admin_headers)
    imp2 = client.get(f"/api/product-hierarchy/import/{up2['job_id']}/impact",
                      headers=admin_headers).json()
    assert imp2["nodes"]["hernoemd"] == 1
    assert imp2["nodes"]["verplaatst"] == 1
    assert imp2["assignments"]["verplaatst"] == 1

    res2 = client.post(f"/api/product-hierarchy/import/{up2['job_id']}/apply",
                       headers=admin_headers).json()
    assert res2["stats"]["nodes_hernoemd"] == 1
    assert res2["stats"]["assignments_verplaatst"] == 1

    # oude toewijzing is superseded, niet verwijderd
    db = SessionLocal()
    try:
        A = models.ProductHierarchyAssignment
        rows = db.query(A).filter(A.sku_id == sku1).order_by(A.id).all()
        assert [a.status for a in rows] == ["superseded", "active"]
    finally:
        db.close()

    # wijzigingshistorie bevat rename/move
    changes = client.get("/api/product-hierarchy/changes?limit=200",
                         headers=admin_headers).json()
    types = {c["change_type"] for c in changes
             if (c.get("sku_id") or "").startswith(PFX)
             or PFX in str(c.get("new_value") or {})
             or PFX in str(c.get("old_value") or {})}
    assert "node_renamed" in types and "node_moved" in types
    assert "assignment_moved" in types


def test_match_op_feed_product_id(client, admin_headers, ph_products):
    """Productcodes uit een hiërarchie-export zijn vaak feed-product-id's
    (raw_attributes.id), geen sku/EAN/OEM — de matcher moet die koppelen."""
    sku1, sku2 = ph_products
    feed_id = f"{PFX}-FEED-9001"
    db = SessionLocal()
    p = db.query(models.DimProduct).filter(models.DimProduct.sku_id == sku1).one()
    p.raw_attributes = {"id": feed_id, "title": "feed product"}
    db.commit()
    db.close()

    content = _csv([
        f"{PFX}-F1,{feed_id},{PFX}-FeedCat > {PFX}-FeedSub",
    ])
    up = _upload(client, admin_headers, content)
    val = client.post(f"/api/product-hierarchy/import/{up['job_id']}/validate",
                      headers=admin_headers).json()
    assert val["counts"]["gekoppeld"] == 1
    assert val["counts"]["niet_gevonden"] == 0

    db = SessionLocal()
    row = (db.query(models.ProductHierarchyStagingRow)
           .filter(models.ProductHierarchyStagingRow.job_id == up["job_id"]).one())
    assert row.matched_sku_id == sku1
    assert row.match_method == "feed_id"
    db.query(models.ProductHierarchyStagingRow).filter(
        models.ProductHierarchyStagingRow.job_id == up["job_id"]).delete()
    db.commit()
    db.close()


def test_validatie_fouten(client, admin_headers, ph_products):
    content = _csv([
        f"{PFX}-OX,,",                                        # leeg pad
        f"{PFX}-OY,{ph_products[0]},{' > '.join([f'{PFX}-N{i}' for i in range(9)])}",  # te diep
        f"{PFX}-OZ,{ph_products[0]},{PFX}-Foo > {PFX}-Bar",
        f"{PFX}-OZ,{ph_products[1]},{PFX}-Foo > {PFX}-Anders",  # optionId-conflict
    ])
    up = _upload(client, admin_headers, content)
    val = client.post(f"/api/product-hierarchy/import/{up['job_id']}/validate",
                      headers=admin_headers).json()
    assert val["counts"]["fouten"] == 3
    assert val["counts"]["geldig"] == 1


def test_sku_conflict_in_bestand(client, admin_headers, ph_products):
    """Zelfde product naar twee verschillende paden = validatiefout."""
    content = _csv([
        f"{PFX}-C1,{ph_products[0]},{PFX}-CA > {PFX}-CB",
        f"{PFX}-C2,{ph_products[0]},{PFX}-CA > {PFX}-CC",
    ])
    up = _upload(client, admin_headers, content)
    val = client.post(f"/api/product-hierarchy/import/{up['job_id']}/validate",
                      headers=admin_headers).json()
    assert val["counts"]["fouten"] == 1
    assert val["counts"]["gekoppeld"] == 1


def test_deactivate_missing_optin(client, admin_headers, ph_products):
    """Met deactivate_missing worden verdwenen import-nodes gedeactiveerd.

    Let op: deactivate_missing werkt globaal over alle import-nodes (dat is
    de productsemantiek: het bestand is een volledige vervanging). In deze
    gedeelde test-DB moeten we daarom vooraf de actieve, niet-test nodes
    vastleggen en achteraf herstellen, anders wist deze test de echte boom.
    """
    db = SessionLocal()
    N = models.ProductHierarchyNode
    pre_active_ids = [nid for (nid,) in db.query(N.id).filter(
        N.is_active == True,  # noqa: E712
        N.source == "import",
        ~N.name.like(f"%{PFX}%"))]
    db.close()
    try:
        _deactivate_missing_scenario(client, admin_headers, ph_products)
    finally:
        db = SessionLocal()
        if pre_active_ids:
            db.query(N).filter(N.id.in_(pre_active_ids)).update(
                {"is_active": True, "valid_to": None}, synchronize_session=False)
            db.commit()
        db.close()


def _deactivate_missing_scenario(client, admin_headers, ph_products):
    up = _upload(client, admin_headers, _csv([
        f"{PFX}-D1,{ph_products[0]},{PFX}-DRoot > {PFX}-DA",
        f"{PFX}-D2,{ph_products[1]},{PFX}-DRoot > {PFX}-DB",
    ]))
    client.post(f"/api/product-hierarchy/import/{up['job_id']}/validate", headers=admin_headers)
    client.post(f"/api/product-hierarchy/import/{up['job_id']}/apply", headers=admin_headers)

    up2 = _upload(client, admin_headers, _csv([
        f"{PFX}-D1,{ph_products[0]},{PFX}-DRoot > {PFX}-DA",
    ]))
    client.post(f"/api/product-hierarchy/import/{up2['job_id']}/validate", headers=admin_headers)
    res = client.post(
        f"/api/product-hierarchy/import/{up2['job_id']}/apply?deactivate_missing=true",
        headers=admin_headers).json()
    assert res["stats"].get("nodes_gedeactiveerd", 0) >= 1
    db = SessionLocal()
    try:
        N = models.ProductHierarchyNode
        db_node = db.query(N).filter(N.external_option_id == f"{PFX}-D2").first()
        assert db_node is not None and db_node.is_active is False
    finally:
        db.close()


def test_padonly_import_impact_matcht_apply(client, admin_headers, ph_products):
    """Zonder optionId-kolom (pad-only) moet de impactanalyse dezelfde
    assignment-statistieken geven als de daadwerkelijke apply — ook bij
    een ongewijzigde herimport (0 verplaatst)."""
    def csv_paths(rows):
        return "productcode,pad\n" + "\n".join(rows)

    content = csv_paths([
        f"{ph_products[0]},{PFX}-PRoot > {PFX}-PA",
        f"{ph_products[1]},{PFX}-PRoot > {PFX}-PB",
    ]).encode()
    up = _upload(client, admin_headers, content)
    client.post(f"/api/product-hierarchy/import/{up['job_id']}/validate", headers=admin_headers)
    impact = client.get(f"/api/product-hierarchy/import/{up['job_id']}/impact",
                         headers=admin_headers).json()
    res = client.post(f"/api/product-hierarchy/import/{up['job_id']}/apply",
                      headers=admin_headers).json()
    assert impact["assignments"]["nieuw"] == res["stats"]["assignments_nieuw"]
    assert impact["assignments"]["verplaatst"] == res["stats"]["assignments_verplaatst"]

    # ongewijzigde herimport: impact én apply melden 0 nieuw / 0 verplaatst
    up2 = _upload(client, admin_headers, content)
    client.post(f"/api/product-hierarchy/import/{up2['job_id']}/validate", headers=admin_headers)
    impact2 = client.get(f"/api/product-hierarchy/import/{up2['job_id']}/impact",
                          headers=admin_headers).json()
    assert impact2["assignments"]["nieuw"] == 0
    assert impact2["assignments"]["verplaatst"] == 0
    assert impact2["assignments"]["ongewijzigd"] == 2
    res2 = client.post(f"/api/product-hierarchy/import/{up2['job_id']}/apply",
                       headers=admin_headers).json()
    assert res2["stats"]["assignments_nieuw"] == 0
    assert res2["stats"]["assignments_verplaatst"] == 0


def test_apply_geblokkeerd_bij_validatiefouten(client, admin_headers, ph_products):
    """Validatiefouten blokkeren apply; force_partial=true past alleen
    de geldige rijen toe (expliciete opt-in)."""
    content = _csv([
        f"{PFX}-E1,{ph_products[0]},{PFX}-EA > {PFX}-EB",
        f"{PFX}-E2,{ph_products[0]},{PFX}-EA > {PFX}-EC",  # sku-conflict → fout
    ])
    up = _upload(client, admin_headers, content)
    val = client.post(f"/api/product-hierarchy/import/{up['job_id']}/validate",
                      headers=admin_headers).json()
    assert val["kan_toepassen"] is False
    assert val["kan_gedeeltelijk_toepassen"] is True
    r = client.post(f"/api/product-hierarchy/import/{up['job_id']}/apply",
                    headers=admin_headers)
    assert r.status_code == 409
    r2 = client.post(f"/api/product-hierarchy/import/{up['job_id']}/apply?force_partial=true",
                     headers=admin_headers)
    assert r2.status_code == 200


def test_upload_zonder_hierarchiekolommen(client, admin_headers):
    content = b"foo,bar\n1,2\n"
    r = client.post("/api/product-hierarchy/import/upload", headers=admin_headers,
                    files={"file": ("x.csv", io.BytesIO(content), "text/csv")})
    assert r.status_code == 400


def test_mutaties_vereisen_rol(client, viewer_headers):
    r = client.post("/api/product-hierarchy/import/upload", headers=viewer_headers,
                    files={"file": ("x.csv", io.BytesIO(b"path\nA > B\n"), "text/csv")})
    assert r.status_code == 403
    # lezen mag wel
    r = client.get("/api/product-hierarchy/stats", headers=viewer_headers)
    assert r.status_code == 200


def test_node_patch_rename_en_cycle_guard(client, admin_headers, ph_products):
    up = _upload(client, admin_headers, _csv([
        f"{PFX}-P1,{ph_products[0]},{PFX}-Root > {PFX}-Sub > {PFX}-Leaf",
    ]))
    client.post(f"/api/product-hierarchy/import/{up['job_id']}/validate", headers=admin_headers)
    client.post(f"/api/product-hierarchy/import/{up['job_id']}/apply", headers=admin_headers)
    root = client.get(f"/api/product-hierarchy/search?q={PFX}-Root",
                      headers=admin_headers).json()[0]
    sub = client.get(f"/api/product-hierarchy/search?q={PFX}-Sub",
                     headers=admin_headers).json()[0]
    # rename
    r = client.patch(f"/api/product-hierarchy/nodes/{sub['id']}",
                     headers=admin_headers, json={"name": f"{PFX}-SubNieuw"})
    assert r.status_code == 200 and r.json()["name"] == f"{PFX}-SubNieuw"
    # cycle guard: root onder eigen subtree hangen
    r = client.patch(f"/api/product-hierarchy/nodes/{root['id']}",
                     headers=admin_headers, json={"parent_id": sub["id"]})
    assert r.status_code == 400


def test_stats_verdeling_per_bron(client, admin_headers, ph_products):
    """Stats splitsen gekoppelde producten uit per herkomst (import/auto_import/manual)."""
    from datetime import datetime
    up = _upload(client, admin_headers, _csv([
        f"{PFX}-B1,{ph_products[0]},{PFX}-Root > {PFX}-BronLeaf",
    ]))
    client.post(f"/api/product-hierarchy/import/{up['job_id']}/validate", headers=admin_headers)
    client.post(f"/api/product-hierarchy/import/{up['job_id']}/apply", headers=admin_headers)

    # tweede product handmatig via auto_import-bron koppelen (direct in DB)
    db = SessionLocal()
    try:
        N = models.ProductHierarchyNode
        leaf = db.query(N).filter(N.path_names.like(f"%{PFX}-BronLeaf%")).first()
        assert leaf is not None
        db.add(models.ProductHierarchyAssignment(
            sku_id=ph_products[1], node_id=leaf.id, status="active",
            valid_from=datetime.utcnow(), source="auto_import",
            assigned_by="test"))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/product-hierarchy/stats", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    verdeling = data.get("gekoppeld_per_bron")
    assert verdeling is not None
    for key in ("import", "auto_import", "manual"):
        assert key in verdeling
    assert verdeling["import"] >= 1
    assert verdeling["auto_import"] >= 1


def test_tree_telt_subtree_producten(client, admin_headers, ph_products):
    """/tree en /children tellen producten inclusief onderliggende nodes."""
    from datetime import datetime as _dt
    db = SessionLocal()
    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    try:
        root = N(name=f"{PFX}-SubRoot", level=1,
                 path_names=f"{PFX}-SubRoot", is_active=True)
        db.add(root); db.flush()
        root.path = f"/{root.id}/"
        mid = N(name=f"{PFX}-SubMid", parent_id=root.id, level=2,
                path_names=f"{PFX}-SubRoot > {PFX}-SubMid", is_active=True)
        db.add(mid); db.flush()
        mid.path = f"{root.path}{mid.id}/"
        leaf = N(name=f"{PFX}-SubLeaf", parent_id=mid.id, level=3,
                 path_names=f"{PFX}-SubRoot > {PFX}-SubMid > {PFX}-SubLeaf",
                 is_active=True)
        db.add(leaf); db.flush()
        leaf.path = f"{mid.path}{leaf.id}/"
        # 1 product direct op mid, 1 op de leaf; root heeft géén directe
        db.add(A(sku_id=ph_products[0], node_id=mid.id, status="active",
                 valid_from=_dt.utcnow(), source="manual", assigned_by="test"))
        db.add(A(sku_id=ph_products[1], node_id=leaf.id, status="active",
                 valid_from=_dt.utcnow(), source="manual", assigned_by="test"))
        db.commit()
        root_id, mid_id, leaf_id = root.id, mid.id, leaf.id
    finally:
        db.close()

    # /tree: root krijgt de subtree-som (2), mid 2 (eigen + leaf), leaf 1
    r = client.get(f"/api/product-hierarchy/tree?root_id={root_id}&depth=8",
                   headers=admin_headers)
    assert r.status_code == 200, r.text
    tree = r.json()
    assert tree["sku_count"] == 2
    mid_node = tree["children"][0]
    assert mid_node["id"] == mid_id and mid_node["sku_count"] == 2
    leaf_node = mid_node["children"][0]
    assert leaf_node["id"] == leaf_id and leaf_node["sku_count"] == 1

    # roots-lijst (depth=1, zoals de HierarchyFilter) toont ook de subtree-som
    r = client.get("/api/product-hierarchy/tree?depth=1", headers=admin_headers)
    assert r.status_code == 200
    by_id = {n["id"]: n for n in r.json()["roots"]}
    assert by_id[root_id]["sku_count"] == 2

    # /children (lazy load) telt eveneens inclusief descendants
    r = client.get(f"/api/product-hierarchy/nodes/{root_id}/children",
                   headers=admin_headers)
    assert r.status_code == 200
    kids = {n["id"]: n for n in r.json()}
    assert kids[mid_id]["sku_count"] == 2


def test_testimport_kan_geen_laatst_toegepaste_import_blijven(
        client, admin_headers, ph_products):
    """Bewaakt de opruimafspraak: een test-apply mag na cleanup nooit de
    "laatst toegepaste import" zijn — anders koppelt auto_assign_new_products
    echte feed-producten nooit meer aan de echte Excel-boom (incident 25-08)."""
    from services.product_hierarchy import last_applied_import
    sku1, _ = ph_products

    db = SessionLocal()
    try:
        voor = last_applied_import(db)
        voor_id = voor.id if voor else None

        up = _upload(client, admin_headers, _csv([
            f"{PFX}-GO1,{sku1},{PFX}-Guard > {PFX}-GuardLeaf",
        ]))
        r = client.post(f"/api/product-hierarchy/import/{up['job_id']}/validate",
                        headers=admin_headers)
        assert r.status_code == 200, r.text
        r = client.post(f"/api/product-hierarchy/import/{up['job_id']}/apply",
                        headers=admin_headers)
        assert r.status_code == 200, r.text

        db.expire_all()
        na = last_applied_import(db)
        # 1) déze apply is nu de laatst toegepaste en herkenbaar aan de
        #    PFX-bestandsnaam (dus opruimbaar door de teardown) …
        assert na is not None and na.id == up["job_id"]
        assert na.filename.startswith(PFX)

        # 2) … en de teardown-opruimlogica herstelt de oude situatie.
        A = models.ProductHierarchyAssignment
        C = models.ProductHierarchyChangeLog
        S = models.ProductHierarchyStagingRow
        J = models.ImportJob
        job_ids = [j for (j,) in db.query(J.id).filter(
            J.upload_type == "product_hierarchy",
            J.filename.like(f"{PFX}%"))]
        db.query(A).filter(A.import_job_id.in_(job_ids)).update(
            {A.import_job_id: None}, synchronize_session=False)
        db.query(C).filter(C.import_job_id.in_(job_ids)).delete(
            synchronize_session=False)
        db.query(S).filter(S.job_id.in_(job_ids)).delete(
            synchronize_session=False)
        db.query(J).filter(J.id.in_(job_ids)).delete(synchronize_session=False)
        db.commit()

        hersteld = last_applied_import(db)
        assert (hersteld.id if hersteld else None) == voor_id
    finally:
        db.close()
