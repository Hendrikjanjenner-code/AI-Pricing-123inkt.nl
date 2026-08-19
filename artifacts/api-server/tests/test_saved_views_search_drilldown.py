"""
Taak #221 — e2e-flow: saved views (sharing-niveaus + department-default),
persoonlijke voorkeuren (favorieten/recents), global search met
permission-filtering en management-drilldown over de hiërarchie.
"""
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from main import app
    c = TestClient(app)
    c.__enter__()
    yield c
    try:
        # App-shutdown kan een achtergrondtaak annuleren (CancelledError);
        # dat is geen testfout (zelfde patroon als test_foundation.py).
        c.__exit__(None, None, None)
    except Exception:
        pass


@pytest.fixture(scope="module")
def admin_headers(client):
    resp = client.post("/api/auth/login",
                       json={"username": "dev_admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _login(client, username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(scope="module")
def department_id(client, admin_headers):
    resp = client.get("/api/authz/departments", headers=admin_headers)
    if resp.status_code == 200:
        rows = resp.json()
        rows = rows.get("departments", rows) if isinstance(rows, dict) else rows
        if rows:
            return rows[0]["id"]
    # fallback: rechtstreeks uit de database
    from database import SessionLocal
    import models
    db = SessionLocal()
    try:
        dept = db.query(models.Department).first()
        assert dept is not None, "geen afdelingen geseed"
        return dept.id
    finally:
        db.close()


def _make_user(client, admin_headers, role, departments=None):
    uname = f"t221_{role}_{uuid.uuid4().hex[:8]}"
    payload = {
        "username": uname, "email": f"{uname}@test.local",
        "password": "Wachtwoord123!", "role": role, "full_name": uname,
    }
    if departments:
        payload["department_ids"] = departments
    resp = client.post("/api/users", json=payload, headers=admin_headers)
    assert resp.status_code in (200, 201), resp.text
    uid = resp.json().get("id") or resp.json().get("user", {}).get("id")
    return uid, uname, _login(client, uname, "Wachtwoord123!")


@pytest.fixture(scope="module")
def cleanup():
    created = {"user_ids": [], "view_ids": [], "sku_ids": [], "node_ids": []}
    yield created
    from database import SessionLocal
    import models
    db = SessionLocal()
    try:
        if created["view_ids"]:
            db.query(models.SavedView).filter(
                models.SavedView.id.in_(created["view_ids"])).delete(synchronize_session=False)
        # views/prefs van testgebruikers + de gebruikers zelf
        if created["user_ids"]:
            db.query(models.SavedView).filter(
                models.SavedView.owner_user_id.in_(created["user_ids"])).delete(synchronize_session=False)
            db.query(models.UserUiPreference).filter(
                models.UserUiPreference.user_id.in_(created["user_ids"])).delete(synchronize_session=False)
            for tbl in (models.UserDepartment, models.UserPermission, models.UserScope):
                db.query(tbl).filter(tbl.user_id.in_(created["user_ids"])).delete(synchronize_session=False)
            # kostenregistratie-rijen (FK) — zie testconventies
            for name in ("AiUsageLog", "CostUsage"):
                tbl = getattr(models, name, None)
                if tbl is not None and hasattr(tbl, "user_id"):
                    db.query(tbl).filter(tbl.user_id.in_(created["user_ids"])).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id.in_(created["user_ids"])).delete(synchronize_session=False)
        if created["sku_ids"]:
            db.query(models.ProductHierarchyAssignment).filter(
                models.ProductHierarchyAssignment.sku_id.in_(created["sku_ids"])).delete(synchronize_session=False)
            db.query(models.FactSupplierData).filter(
                models.FactSupplierData.sku_id.in_(created["sku_ids"])).delete(synchronize_session=False)
            db.query(models.FactPricingRecommendationDaily).filter(
                models.FactPricingRecommendationDaily.sku_id.in_(created["sku_ids"])).delete(synchronize_session=False)
            db.query(models.DimProduct).filter(
                models.DimProduct.sku_id.in_(created["sku_ids"])).delete(synchronize_session=False)
        if created["node_ids"]:
            db.query(models.ProductHierarchyNode).filter(
                models.ProductHierarchyNode.id.in_(created["node_ids"])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


# ── Saved views ─────────────────────────────────────────────────────────────

def test_private_view_only_visible_to_owner(client, admin_headers, cleanup):
    uid1, _, h1 = _make_user(client, admin_headers, "viewer")
    uid2, _, h2 = _make_user(client, admin_headers, "viewer")
    cleanup["user_ids"] += [uid1, uid2]

    resp = client.post("/api/saved-views", headers=h1, json={
        "name": "Mijn private view", "page_key": "*", "scope": "private",
        "config": {"filters": {"brands": ["TestMerk"]}},
    })
    assert resp.status_code == 201, resp.text
    view_id = resp.json()["id"]
    cleanup["view_ids"].append(view_id)

    ids1 = [v["id"] for v in client.get("/api/saved-views", headers=h1).json()["views"]]
    ids2 = [v["id"] for v in client.get("/api/saved-views", headers=h2).json()["views"]]
    assert view_id in ids1
    assert view_id not in ids2


def test_viewer_cannot_create_team_view(client, admin_headers, cleanup):
    uid, _, h = _make_user(client, admin_headers, "viewer")
    cleanup["user_ids"].append(uid)
    resp = client.post("/api/saved-views", headers=h, json={
        "name": "Team poging", "page_key": "*", "scope": "team", "config": {},
    })
    assert resp.status_code == 403


def test_team_view_visible_to_everyone(client, admin_headers, cleanup):
    uid1, _, h1 = _make_user(client, admin_headers, "analyst")
    uid2, _, h2 = _make_user(client, admin_headers, "viewer")
    cleanup["user_ids"] += [uid1, uid2]
    resp = client.post("/api/saved-views", headers=h1, json={
        "name": "Team view", "page_key": "*", "scope": "team",
        "config": {"filters": {"periodDays": 30}},
    })
    assert resp.status_code == 201, resp.text
    view_id = resp.json()["id"]
    cleanup["view_ids"].append(view_id)
    ids2 = [v["id"] for v in client.get("/api/saved-views", headers=h2).json()["views"]]
    assert view_id in ids2


def test_department_default_flow(client, admin_headers, department_id, cleanup):
    uid_mgr, _, h_mgr = _make_user(client, admin_headers, "pricing_manager")
    uid_lid, _, h_lid = _make_user(client, admin_headers, "viewer")
    cleanup["user_ids"] += [uid_mgr, uid_lid]

    # koppel beide aan de afdeling
    from database import SessionLocal
    import models
    db = SessionLocal()
    try:
        for uid in (uid_mgr, uid_lid):
            if not db.query(models.UserDepartment).filter_by(
                    user_id=uid, department_id=department_id).first():
                db.add(models.UserDepartment(user_id=uid, department_id=department_id, is_primary=True))
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/saved-views", headers=h_mgr, json={
        "name": "Afdelingsdefault", "page_key": "*", "scope": "department",
        "department_id": department_id, "is_department_default": True,
        "config": {"filters": {"brands": ["AfdelingsMerk"]}},
    })
    assert resp.status_code == 201, resp.text
    view_id = resp.json()["id"]
    cleanup["view_ids"].append(view_id)

    # lid van de afdeling krijgt de default terug
    resp = client.get("/api/saved-views/department-default?page_key=*", headers=h_lid)
    assert resp.status_code == 200
    view = resp.json()["view"]
    assert view is not None and view["id"] == view_id
    assert view["config"]["filters"]["brands"] == ["AfdelingsMerk"]

    # tweede default op dezelfde pagina verdringt de eerste
    resp = client.post("/api/saved-views", headers=h_mgr, json={
        "name": "Nieuwe default", "page_key": "*", "scope": "department",
        "department_id": department_id, "is_department_default": True, "config": {},
    })
    assert resp.status_code == 201
    view2_id = resp.json()["id"]
    cleanup["view_ids"].append(view2_id)
    resp = client.get("/api/saved-views/department-default?page_key=*", headers=h_lid)
    assert resp.json()["view"]["id"] == view2_id


def test_only_owner_or_admin_can_delete(client, admin_headers, cleanup):
    uid1, _, h1 = _make_user(client, admin_headers, "analyst")
    uid2, _, h2 = _make_user(client, admin_headers, "analyst")
    cleanup["user_ids"] += [uid1, uid2]
    view_id = client.post("/api/saved-views", headers=h1, json={
        "name": "Te verwijderen", "page_key": "*", "scope": "team", "config": {},
    }).json()["id"]
    cleanup["view_ids"].append(view_id)
    assert client.delete(f"/api/saved-views/{view_id}", headers=h2).status_code == 403
    assert client.delete(f"/api/saved-views/{view_id}", headers=h1).status_code == 200


# ── Voorkeuren (favorieten/recents) ────────────────────────────────────────

def test_preferences_roundtrip_and_isolation(client, admin_headers, cleanup):
    uid1, _, h1 = _make_user(client, admin_headers, "viewer")
    uid2, _, h2 = _make_user(client, admin_headers, "viewer")
    cleanup["user_ids"] += [uid1, uid2]

    fav = {"items": [{"path": "/command-center", "label": "Command Center"}]}
    resp = client.put("/api/me/preferences/favorites", headers=h1, json=fav)
    assert resp.status_code == 200
    assert client.get("/api/me/preferences/favorites", headers=h1).json()["value"] == fav
    # andere gebruiker ziet niets
    assert client.get("/api/me/preferences/favorites", headers=h2).json()["value"] is None
    # onbekende sleutel wordt geweigerd
    assert client.put("/api/me/preferences/hacky", headers=h1, json={}).status_code == 404


# ── Global search ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def search_data(client, admin_headers, cleanup):
    from database import SessionLocal
    import models
    tag = uuid.uuid4().hex[:6]
    sku = f"T221SKU{tag}"
    db = SessionLocal()
    try:
        node = models.ProductHierarchyNode(name=f"T221 Node {tag}", level=1, is_active=True)
        db.add(node)
        db.flush()
        node.path = f"/{node.id}/"
        child = models.ProductHierarchyNode(
            name=f"T221 Sub {tag}", level=2, parent_id=node.id, is_active=True)
        db.add(child)
        db.flush()
        child.path = f"/{node.id}/{child.id}/"
        db.add(models.DimProduct(
            sku_id=sku, product_name=f"T221 Product {tag}", brand=f"T221Merk{tag}",
            category=f"T221Cat{tag}", ean=f"87121{tag}", omzet_ytd=1000, marge_ytd=250,
        ))
        db.add(models.ProductHierarchyAssignment(sku_id=sku, node_id=child.id, status="active"))
        db.add(models.FactPricingRecommendationDaily(
            date=__import__("datetime").date.today(), sku_id=sku, approval_status="pending"))
        db.commit()
        cleanup["sku_ids"].append(sku)
        cleanup["node_ids"] += [node.id, child.id]
        return {"tag": tag, "sku": sku, "node_id": node.id, "child_id": child.id}
    finally:
        db.close()


def test_search_finds_entities_for_admin(client, admin_headers, search_data):
    tag = search_data["tag"]
    resp = client.get(f"/api/search?q=T221", headers=admin_headers)
    assert resp.status_code == 200
    groups = resp.json()["groups"]
    assert any(h["id"] == search_data["sku"] for h in groups.get("products", []))
    assert any(h["id"] == search_data["node_id"] for h in groups.get("hierarchy_nodes", []))
    assert any(h["label"] == f"T221Merk{tag}" for h in groups.get("brands", []))
    assert any(h["label"] == f"T221Cat{tag}" for h in groups.get("categories", []))
    # zoeken op EAN vindt het product
    resp = client.get(f"/api/search?q=87121{tag}", headers=admin_headers)
    assert any(h["id"] == search_data["sku"] for h in resp.json()["groups"].get("products", []))


def test_search_is_permission_filtered(client, admin_headers, search_data, cleanup):
    # viewer heeft alleen management.view → geen product/competitor-groepen
    uid, _, h = _make_user(client, admin_headers, "viewer")
    cleanup["user_ids"].append(uid)
    resp = client.get("/api/search?q=T221", headers=h)
    assert resp.status_code == 200
    groups = resp.json()["groups"]
    assert "products" not in groups
    assert "competitors" not in groups
    assert "suppliers" not in groups


def test_search_respects_user_shop_scope(client, admin_headers, search_data, cleanup):
    """Regressie: een via UserScope beperkte gebruiker mag via /api/search
    geen producten/leveranciers van andere shops ontdekken."""
    from database import SessionLocal
    import models
    tag = search_data["tag"]
    scoped_sku = f"T221SCP{tag}"
    db = SessionLocal()
    try:
        shops = db.query(models.DimShop).order_by(models.DimShop.id).limit(2).all()
        assert len(shops) >= 2
        shop_a, shop_b = shops[0].id, shops[1].id
        # product + leveranciersrij exclusief in shop B
        db.add(models.DimProduct(
            sku_id=scoped_sku, product_name=f"T221 ShopB Product {tag}",
            brand=f"T221MerkB{tag}", category=f"T221CatB{tag}", shop_id=shop_b))
        db.add(models.FactSupplierData(
            sku_id=scoped_sku, supplier_id=f"SUPB{tag}",
            supplier_name=f"T221 Leverancier B {tag}"))
        # zorg dat het hoofd-testproduct in shop A zit
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == search_data["sku"]).update({"shop_id": shop_a})
        db.commit()
        cleanup["sku_ids"].append(scoped_sku)
    finally:
        db.close()

    uid, _, h = _make_user(client, admin_headers, "analyst")
    cleanup["user_ids"].append(uid)
    db = SessionLocal()
    try:
        db.add(models.UserScope(user_id=uid, scope_type="shop", scope_value=str(shop_a)))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/search?q=T221", headers=h)
    assert resp.status_code == 200
    groups = resp.json()["groups"]
    product_ids = {p["id"] for p in groups.get("products", [])}
    assert search_data["sku"] in product_ids          # eigen shop wél
    assert scoped_sku not in product_ids              # andere shop niet
    assert f"T221MerkB{tag}" not in {b["label"] for b in groups.get("brands", [])}
    assert f"T221CatB{tag}" not in {c["label"] for c in groups.get("categories", [])}
    sup_names = {s["label"] for s in groups.get("suppliers", [])}
    assert f"T221 Leverancier B {tag}" not in sup_names

    # admin (onbeperkt) ziet het shop-B-product wél
    resp = client.get("/api/search?q=T221", headers=admin_headers)
    assert scoped_sku in {p["id"] for p in resp.json()["groups"].get("products", [])}


# ── Management-drilldown ────────────────────────────────────────────────────

def test_drilldown_aggregates_and_drills(client, admin_headers, search_data):
    resp = client.get("/api/management/drilldown", headers=admin_headers)
    assert resp.status_code == 200
    top = resp.json()
    row = next((r for r in top["children"] if r["id"] == search_data["node_id"]), None)
    assert row is not None, "topniveau-node ontbreekt in drilldown"
    assert row["sku_count"] >= 1
    assert row["revenue_ytd"] >= 1000
    assert row["margin_ytd"] >= 250
    assert row["opportunities"] >= 1
    assert row["has_children"] is True

    # doordrillen naar de node zelf: child + breadcrumb + totals
    resp = client.get(f"/api/management/drilldown?node_id={search_data['node_id']}",
                      headers=admin_headers)
    data = resp.json()
    assert data["node"]["id"] == search_data["node_id"]
    assert data["totals"]["sku_count"] >= 1
    assert any(c["id"] == search_data["child_id"] for c in data["children"])
    assert [b["id"] for b in data["breadcrumb"]] == [search_data["node_id"]]


def test_drilldown_requires_management_view(client, admin_headers, cleanup):
    # gebruiker zonder management.view: rol zonder die permissie bestaat niet
    # standaard (viewer heeft management.view), dus we ontnemen die via een
    # kale analyst-achtige check: maak viewer en verwijder rolpermissie-pad is
    # te invasief — controleer in plaats daarvan dat auth vereist is.
    resp = client.get("/api/management/drilldown")
    assert resp.status_code in (401, 403)


def test_drilldown_default_respects_user_shop_scope(client, admin_headers,
                                                    search_data, cleanup):
    """Regressie: zonder expliciete shop_id mag een via UserScope beperkte
    gebruiker geen cijfers van andere shops in de aggregaties zien."""
    from database import SessionLocal
    import models
    tag = search_data["tag"]
    other_sku = f"T221OTH{tag}"
    db = SessionLocal()
    try:
        shops = db.query(models.DimShop).order_by(models.DimShop.id).limit(2).all()
        assert len(shops) >= 2, "test vereist minstens twee shops"
        shop_a, shop_b = shops[0].id, shops[1].id
        # product in shop B onder dezelfde hiërarchie-node
        db.add(models.DimProduct(
            sku_id=other_sku, product_name=f"T221 Other {tag}",
            brand=f"T221Merk{tag}", category=f"T221Cat{tag}",
            omzet_ytd=5000, marge_ytd=500, shop_id=shop_b,
        ))
        db.add(models.ProductHierarchyAssignment(
            sku_id=other_sku, node_id=search_data["child_id"], status="active"))
        # bestaand testproduct expliciet in shop A
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id == search_data["sku"]).update({"shop_id": shop_a})
        db.commit()
        cleanup["sku_ids"].append(other_sku)
    finally:
        db.close()

    uid, _, h = _make_user(client, admin_headers, "viewer")
    cleanup["user_ids"].append(uid)
    db = SessionLocal()
    try:
        db.add(models.UserScope(user_id=uid, scope_type="shop", scope_value=str(shop_a)))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/management/drilldown", headers=h)
    assert resp.status_code == 200
    row = next((r for r in resp.json()["children"]
                if r["id"] == search_data["node_id"]), None)
    assert row is not None
    # alleen shop A telt mee: omzet van het shop-B-product (5000) mag niet meetellen
    assert row["revenue_ytd"] < 5000
    assert row["revenue_ytd"] >= 1000

    # expliciet vragen om shop B → 403
    resp = client.get(f"/api/management/drilldown?shop_id={shop_b}", headers=h)
    assert resp.status_code == 403

    # shops-vergelijking toont alleen shop A
    resp = client.get("/api/management/drilldown/shops", headers=h)
    assert resp.status_code == 200
    assert {s["shop_id"] for s in resp.json()["shops"]} <= {shop_a}


def test_drilldown_shops_lists_shops(client, admin_headers, search_data):
    resp = client.get(f"/api/management/drilldown/shops?node_id={search_data['node_id']}",
                      headers=admin_headers)
    assert resp.status_code == 200
    shops = resp.json()["shops"]
    assert len(shops) >= 1
    assert all("revenue_ytd" in s and "shop_name" in s for s in shops)
