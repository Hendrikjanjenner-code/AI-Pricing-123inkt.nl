"""
Granulaire autorisatie (taak 219): departments, permissies en data-scopes.

Onderdelen:
- PERMISSIONS: canonieke permissiecatalogus (code + label + domein).
- ROUTE_PERMISSIONS: Route Registry — API-padsegment → vereiste view-permissie.
  Wordt afgedwongen door de AuthzMiddleware in main.py voor ÉLKE /api-route,
  zodat verboden endpoints ook via directe URL 403 geven (menu-verbergen is
  alleen UX).
- require_permission(code): FastAPI-dependency voor endpoint-niveau checks.
- effective_permissions(db, user): rol-basis ∪ afdeling-defaults ∪ extra's.
- seed_authz(): idempotente seeding van afdelingen + rollenmatrix en een
  eenmalige migratie van bestaande gebruikers zonder toegangsverlies.
"""
import logging
import time
from fastapi import Depends, HTTPException

import models
from auth import get_current_user, VALID_ROLES
from database import SessionLocal

logger = logging.getLogger("uvicorn.error")

# ── Permissiecatalogus ───────────────────────────────────────────────────────
# (code, label, frontend-domein waar de permissie primair bij hoort)
PERMISSIONS: list[dict] = [
    {"code": "competition.view",    "label": "Concurrentie bekijken",        "domein": "concurrentie"},
    {"code": "competition.edit",    "label": "Concurrentie bewerken",        "domein": "concurrentie"},
    {"code": "competition.approve", "label": "Concurrentie-acties goedkeuren","domein": "concurrentie"},
    {"code": "pricing.view",        "label": "Pricing bekijken",             "domein": "pricing"},
    {"code": "pricing.propose",     "label": "Prijsvoorstellen doen",        "domein": "pricing"},
    {"code": "pricing.approve",     "label": "Prijzen goedkeuren",           "domein": "pricing"},
    {"code": "catman.view",         "label": "CatMan bekijken",              "domein": "catman"},
    {"code": "supplier.view",       "label": "Inkoop/leveranciers bekijken", "domein": "inkoop"},
    {"code": "supplychain.view",    "label": "Supply chain bekijken",        "domein": "supply-chain"},
    {"code": "seo.view",            "label": "Search & digital bekijken",    "domein": "search-digital"},
    {"code": "promotions.view",     "label": "Promoties & loyalty bekijken", "domein": "promoties-loyalty"},
    {"code": "forecast.view",       "label": "Forecast & risico bekijken",   "domein": "forecast-risico"},
    {"code": "data.view",           "label": "Product & data bekijken",      "domein": "product-data"},
    {"code": "data.edit",           "label": "Product & data bewerken",      "domein": "product-data"},
    {"code": "ai.view",             "label": "AI & besluitvorming bekijken", "domein": "ai-besluitvorming"},
    {"code": "management.view",     "label": "Management bekijken",          "domein": "management"},
    {"code": "audit.view",          "label": "Audit log bekijken",           "domein": "beheer"},
    {"code": "admin.manage",        "label": "Beheer (gebruikers/instellingen)", "domein": "beheer"},
]
PERMISSION_CODES = {p["code"] for p in PERMISSIONS}
ALL_VIEW_PERMISSIONS = sorted(c for c in PERMISSION_CODES if c.endswith(".view"))

# ── Route Registry: API-padsegment (na /api/) → vereiste view-permissie ─────
# None / ontbrekend segment = toegankelijk voor iedere geauthenticeerde
# gebruiker (bestaande get_current_user/require_role-dependencies blijven
# daarnaast onverkort gelden).
ROUTE_PERMISSIONS: dict[str, str] = {
    # Concurrentie
    "competition": "competition.view",
    "concurrentie": "competition.view",
    "monitoring": "competition.view",
    # Pricing
    "recommendations": "pricing.view",
    "cost-priority": "pricing.view",
    "hub-feeds": "pricing.view",
    "channelmanager": "pricing.view",
    "elasticiteit": "pricing.view",
    "break-even": "pricing.view",
    "ppfs": "pricing.view",
    "margebescherming": "pricing.view",
    "execution": "pricing.view",
    "exports": "pricing.view",
    # CatMan
    "bcg": "catman.view",
    "bcg-transities": "catman.view",
    "huismerk-impact": "catman.view",
    "substitutions": "catman.view",
    # Inkoop
    "procurement": "supplier.view",
    "kostprijswijziging": "supplier.view",
    # Supply chain
    "kosten": "supplychain.view",
    # Search & digital
    "traffic": "seo.view",
    "traffic-driver": "seo.view",
    "conversie": "seo.view",
    "search-demand": "seo.view",
    "entry-products": "seo.view",
    # Promoties & loyalty
    "promotion-intelligence": "promotions.view",
    "marketing-vs-korting": "promotions.view",
    "ab-tests": "promotions.view",
    "basket": "promotions.view",
    "basket-intelligence": "promotions.view",
    "cross-sell": "promotions.view",
    "sku-ecosystem": "promotions.view",
    "loyalty": "promotions.view",
    # Forecast & risico
    "forecast": "forecast.view",
    "economie": "forecast.view",
    # Product & data
    "products": "data.view",
    "skus": "data.view",
    "categories": "data.view",
    "category-strategies": "data.view",
    "category-hierarchy": "data.view",
    "product-hierarchy": "data.view",
    "pim": "data.view",
    "data-quality": "data.view",
    "data-sources": "data.view",
    "connectors": "data.view",
    "uploads": "data.view",
    # AI & besluitvorming
    "copilot": "ai.view",
    "decisions": "ai.view",
    "opportunities": "ai.view",
    "model-health": "ai.view",
    "model-registry": "ai.view",
    "model-runs": "ai.view",
    "governance": "ai.view",
    # Management
    "rapportages": "management.view",
    "platform": "management.view",
    "management": "management.view",
    # Beheer
    "audit-log": "audit.view",
    "users": "admin.manage",
    "admin": "admin.manage",
    "shops": "admin.manage",
    "authz": None,  # fijnmazig per endpoint geregeld in routes/authz.py
    # Altijd toegankelijk voor ingelogde gebruikers (command center e.d.)
    "dashboard": None, "command-center": None, "signals": None,
    # Taak #221: zoekresultaten en saved views worden per-endpoint
    # permission-gefilterd; voorkeuren zijn strikt per gebruiker.
    "search": None, "saved-views": None, "me": None,
    "notifications": None, "auth": None, "engine-jobs": None,
    "explainability": None, "bigquery": None, "health": None, "healthz": None,
}

# ── Rol-basis-permissies (nieuw, principieel smal model) ────────────────────
# Bestaande gebruikers worden bij de eenmalige migratie aangevuld met
# LEGACY_ROLE_PERMISSIONS zodat niemand toegang verliest; nieuwe gebruikers
# krijgen hun rechten via rol + afdeling(en) + extra permissies.
ROLE_BASE_PERMISSIONS: dict[str, list[str]] = {
    "admin": sorted(PERMISSION_CODES),
    "pricing_manager": sorted(PERMISSION_CODES - {"admin.manage"}),
    # Analisten konden in het oude model concurrentie-analyses draaien
    # (simulaties e.d.), maar geen data-imports doen.
    "analyst": sorted(set(ALL_VIEW_PERMISSIONS) | {"audit.view", "competition.edit"}),
    "viewer": ["management.view"],
}

# Wat elke rol in het oude model feitelijk kon zien (alle GET-endpoints waren
# enkel get_current_user-beschermd). Gebruikt voor de eenmalige migratie.
LEGACY_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": sorted(PERMISSION_CODES),
    "pricing_manager": sorted(PERMISSION_CODES - {"admin.manage"}),
    "analyst": sorted(set(ALL_VIEW_PERMISSIONS) | {"audit.view", "competition.edit"}),
    "viewer": sorted(ALL_VIEW_PERMISSIONS),
}

# ── Afdelingen (workspaces) ─────────────────────────────────────────────────
DEPARTMENT_SEED: list[dict] = [
    {"code": "catman", "name": "CatMan", "positie": 1,
     "workspace_domains": ["command-center", "concurrentie", "catman", "product-data"],
     "default_permissions": ["competition.view", "competition.edit", "catman.view", "data.view"],
     "default_route": "/bcg/dashboard"},
    {"code": "pricing", "name": "Pricing", "positie": 2,
     "workspace_domains": ["command-center", "concurrentie", "pricing", "ai-besluitvorming", "forecast-risico"],
     "default_permissions": ["pricing.view", "pricing.propose", "competition.view", "ai.view", "forecast.view"],
     "default_route": "/prijsadviezen"},
    {"code": "inkoop", "name": "Inkoop", "positie": 3,
     "workspace_domains": ["command-center", "inkoop", "catman"],
     "default_permissions": ["supplier.view", "catman.view"],
     "default_route": "/kostprijswijziging"},
    {"code": "supply_chain", "name": "Supply Chain", "positie": 4,
     "workspace_domains": ["command-center", "supply-chain", "forecast-risico"],
     "default_permissions": ["supplychain.view", "forecast.view"],
     "default_route": "/kosten/dashboard"},
    {"code": "seo", "name": "SEO/SEA/GEO/AEO", "positie": 5,
     "workspace_domains": ["command-center", "search-digital", "promoties-loyalty"],
     "default_permissions": ["seo.view", "promotions.view"],
     "default_route": "/traffic/dashboard"},
    {"code": "management", "name": "Management", "positie": 6,
     "workspace_domains": ["command-center", "management", "forecast-risico"],
     "default_permissions": ["management.view", "forecast.view"],
     "default_route": "/command-center"},
    {"code": "finance", "name": "Finance", "positie": 7,
     "workspace_domains": ["command-center", "management", "supply-chain", "pricing"],
     "default_permissions": ["management.view", "supplychain.view", "pricing.view"],
     "default_route": "/platform/kosten"},
    {"code": "data_bi", "name": "Data/BI", "positie": 8,
     "workspace_domains": ["command-center", "product-data", "ai-besluitvorming", "forecast-risico"],
     "default_permissions": ["data.view", "ai.view", "forecast.view"],
     "default_route": "/datakwaliteit"},
    {"code": "admin", "name": "Admin", "positie": 9,
     "workspace_domains": ["command-center", "beheer", "product-data", "management"],
     "default_permissions": ["admin.manage", "audit.view", "data.view", "management.view"],
     "default_route": "/instellingen"},
]

# Rol → afdelingscode voor de eenmalige migratie van bestaande gebruikers.
ROLE_TO_DEPARTMENT = {
    "admin": "admin",
    "pricing_manager": "pricing",
    "analyst": "data_bi",
    "viewer": "management",
}

# ── Effectieve permissies (met kleine in-process cache) ────────────────────
_PERM_CACHE: dict[int, tuple[float, frozenset]] = {}
_PERM_CACHE_TTL = 15.0  # seconden


def invalidate_permission_cache(user_id: int | None = None) -> None:
    if user_id is None:
        _PERM_CACHE.clear()
    else:
        _PERM_CACHE.pop(user_id, None)


def effective_permissions(db, user: models.User) -> frozenset:
    """Rol-matrix ∪ afdeling-defaults ∪ gebruikers-extra's. Admin = alles."""
    if user.role == "admin":
        return frozenset(PERMISSION_CODES)

    cached = _PERM_CACHE.get(user.id)
    now = time.monotonic()
    if cached and now - cached[0] < _PERM_CACHE_TTL:
        return cached[1]

    perms: set[str] = set()
    for (code,) in db.query(models.RolePermission.permission_code).filter(
            models.RolePermission.role == user.role):
        perms.add(code)
    dept_rows = (
        db.query(models.Department)
        .join(models.UserDepartment, models.UserDepartment.department_id == models.Department.id)
        .filter(models.UserDepartment.user_id == user.id, models.Department.active.is_(True))
        .all()
    )
    for dept in dept_rows:
        perms.update(dept.default_permissions or [])
    for (code,) in db.query(models.UserPermission.permission_code).filter(
            models.UserPermission.user_id == user.id):
        perms.add(code)

    result = frozenset(perms & PERMISSION_CODES)
    _PERM_CACHE[user.id] = (now, result)
    return result


def user_departments(db, user: models.User) -> list[models.Department]:
    return (
        db.query(models.Department)
        .join(models.UserDepartment, models.UserDepartment.department_id == models.Department.id)
        .filter(models.UserDepartment.user_id == user.id, models.Department.active.is_(True))
        .order_by(models.UserDepartment.is_primary.desc(), models.Department.positie)
        .all()
    )


def workspace_for(db, user: models.User, perms: frozenset) -> dict:
    """Workspace-payload: zichtbare domeinen + default startpagina."""
    depts = user_departments(db, user)
    domains: list[str] = []
    for d in depts:
        for dom in (d.workspace_domains or []):
            if dom not in domains:
                domains.append(dom)
    # Domeinen waarvoor de gebruiker (extra) view-permissies heeft, blijven
    # bereikbaar: cross-department toegang via permissies, geen accounttypen.
    perm_domains = {p["domein"] for p in PERMISSIONS
                    if p["code"] in perms and p["code"].endswith((".view", ".manage"))}
    for dom in perm_domains:
        if dom not in domains:
            domains.append(dom)
    if "command-center" not in domains:
        domains.insert(0, "command-center")
    default_route = depts[0].default_route if depts else "/"
    return {
        "domains": domains,
        "default_route": default_route or "/",
        "primary_department": depts[0].code if depts else None,
    }


def authz_payload(db, user: models.User) -> dict:
    """Extra velden voor /api/auth/me en de loginrespons."""
    perms = effective_permissions(db, user)
    return {
        "permissions": sorted(perms),
        "departments": [
            {"id": d.id, "code": d.code, "name": d.name}
            for d in user_departments(db, user)
        ],
        "workspace": workspace_for(db, user, perms),
        "scopes": [
            {"scope_type": s.scope_type, "scope_value": s.scope_value}
            for s in db.query(models.UserScope).filter(models.UserScope.user_id == user.id)
        ],
    }


def user_allowed_shop_ids(db, user: models.User) -> set[int] | None:
    """Shop-ids waartoe de gebruiker beperkt is; None = onbeperkt."""
    scopes = db.query(models.UserScope).filter(models.UserScope.user_id == user.id).all()
    if not scopes:
        return None
    allowed: set[int] = set()
    for s in scopes:
        if s.scope_type == "shop" and str(s.scope_value).isdigit():
            allowed.add(int(s.scope_value))
        elif s.scope_type == "country":
            for (sid,) in db.query(models.DimShop.id).filter(models.DimShop.country == s.scope_value):
                allowed.add(sid)
        elif s.scope_type == "legal_entity":
            for (sid,) in db.query(models.DimShop.id).filter(models.DimShop.legal_entity == s.scope_value):
                allowed.add(sid)
    return allowed


# ── FastAPI-dependency ──────────────────────────────────────────────────────
def require_permission(code: str):
    """Dependency-factory: eist een specifieke permissie (admin heeft alles)."""
    if code not in PERMISSION_CODES:
        raise ValueError(f"require_permission: onbekende permissie '{code}'")

    def checker(current_user: models.User = Depends(get_current_user)):
        db = SessionLocal()
        try:
            if code not in effective_permissions(db, current_user):
                raise HTTPException(status_code=403, detail=f"Permissie '{code}' vereist")
        finally:
            db.close()
        return current_user
    return checker


def required_permission_for_path(path: str) -> str | None:
    """Route Registry-lookup: /api/<segment>/... → vereiste view-permissie."""
    if not path.startswith("/api/"):
        return None
    segment = path[5:].split("/", 1)[0].split("?", 1)[0]
    return ROUTE_PERMISSIONS.get(segment)


# ── Actie-permissies per mutatie (methode-bewust) ───────────────────────────
# Voor schrijfmethodes (POST/PUT/PATCH/DELETE) geldt naast de view-permissie
# een actie-permissie. Waar een regel bestaat, is de permissie leidend:
# intrekken in de matrix blokkeert de actie, toekennen geeft de capability —
# ook aan rollen die de actie via het oude rollenmodel niet hadden.
_APPROVE_HINTS = ("approve", "reject", "decision", "override", "goedkeur", "afwijz")

# Segment → default schrijf-permissie.
WRITE_PERMISSIONS: dict[str, str] = {
    "hub-feeds": "pricing.propose",
    "channelmanager": "pricing.propose",
    "recommendations": "pricing.propose",
    "recommendation": "pricing.propose",
    "competition": "competition.edit",
    "uploads": "data.edit",
    "pim": "data.edit",
    "products": "data.edit",
    "categories": "data.edit",
    "category-hierarchy": "data.edit",
    "product-hierarchy": "data.edit",
    "connectors": "data.edit",
    "priceshape": "data.edit",
    "drs": "data.edit",
    "users": "admin.manage",
    "admin": "admin.manage",
    "authz": "admin.manage",
}

# Segment → approve-permissie voor paden met een approve/besluit-hint.
APPROVE_PERMISSIONS: dict[str, str] = {
    "channelmanager": "pricing.approve",
    "recommendations": "pricing.approve",
    "recommendation": "pricing.approve",
    "competition": "competition.approve",
}

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def required_action_permission(path: str, method: str) -> str | None:
    """Actie-permissie voor een mutatie; None = geen granulaire regel."""
    if method.upper() not in _WRITE_METHODS or not path.startswith("/api/"):
        return None
    rest = path[5:].split("?", 1)[0]
    segment = rest.split("/", 1)[0]
    lower = rest.lower()
    parts = rest.rstrip("/").split("/")
    # These workflows use explicit handler capabilities, not substring hints.
    # In particular pause and legacy readback are proposals, while printer
    # advice and printer readback require approval.
    if segment == "hub-feeds":
        if (method.upper() == "POST" and len(parts) == 5 and parts[2] == "profiles"
                and parts[4] in {"activate", "release", "token"}):
            return "pricing.approve"
        return WRITE_PERMISSIONS[segment]
    if segment == "channelmanager":
        if method.upper() == "POST":
            if len(parts) == 5 and parts[1] == "channels" and parts[4] == "activate":
                return "pricing.approve"
            if len(parts) >= 2 and parts[1] == "printer":
                if ((len(parts) == 4 and parts[3] == "advice")
                        or (len(parts) == 5 and parts[3] in {"approve", "export", "readback"})):
                    return "pricing.approve"
            elif (len(parts) == 5 and
                  ((parts[2] == "basis" and parts[4] == "approve")
                   or (parts[2] == "calculations" and parts[4] in {"approve", "export"}))):
                return "pricing.approve"
        return WRITE_PERMISSIONS[segment]
    if segment in APPROVE_PERMISSIONS and any(h in lower for h in _APPROVE_HINTS):
        return APPROVE_PERMISSIONS[segment]
    return WRITE_PERMISSIONS.get(segment)


# ── Seeding & migratie ──────────────────────────────────────────────────────
def seed_authz() -> None:
    """
    Idempotent:
    1. Afdelingen aanmaken als er nog geen bestaan.
    2. Rollen & Rechten-matrix vullen als die leeg is.
    3. Eenmalige migratie: bestaande gebruikers krijgen hun afdeling (op basis
       van hun rol) en legacy-permissies als extra's, zodat niemand toegang
       verliest. Draait alleen als er nog geen user_departments zijn.
    """
    db = SessionLocal()
    try:
        if db.query(models.Department.id).first() is None:
            for spec in DEPARTMENT_SEED:
                db.add(models.Department(**spec))
            db.commit()
            logger.info("authz: %d afdelingen geseed.", len(DEPARTMENT_SEED))

        if db.query(models.RolePermission.id).first() is None:
            for role, codes in ROLE_BASE_PERMISSIONS.items():
                for code in codes:
                    db.add(models.RolePermission(role=role, permission_code=code))
            db.commit()
            logger.info("authz: rollenmatrix geseed.")

        migrated_before = db.query(models.UserDepartment.id).first() is not None
        if not migrated_before:
            dept_by_code = {d.code: d for d in db.query(models.Department).all()}
            role_base = {
                role: {c for (c,) in db.query(models.RolePermission.permission_code)
                       .filter(models.RolePermission.role == role)}
                for role in VALID_ROLES
            }
            users = db.query(models.User).all()
            for u in users:
                dept = dept_by_code.get(ROLE_TO_DEPARTMENT.get(u.role, "management"))
                if dept:
                    db.add(models.UserDepartment(user_id=u.id, department_id=dept.id, is_primary=True))
                legacy = set(LEGACY_ROLE_PERMISSIONS.get(u.role, []))
                extras = legacy - role_base.get(u.role, set()) - set(
                    (dept.default_permissions or []) if dept else [])
                for code in sorted(extras):
                    db.add(models.UserPermission(user_id=u.id, permission_code=code,
                                                 granted_by="migratie-taak-219"))
            db.commit()
            if users:
                db.add(models.AuditLog(
                    entity_type="authz", entity_id="migration", action="authz_migration",
                    performed_by="systeem",
                    details=f"{len(users)} bestaande gebruikers gemigreerd naar het "
                            f"department/permissie-model zonder toegangsverlies.",
                ))
                db.commit()
            logger.info("authz: %d bestaande gebruikers gemigreerd.", len(users))
        invalidate_permission_cache()
    except Exception as exc:
        db.rollback()
        logger.error("seed_authz mislukt (niet-fataal): %s", exc, exc_info=True)
    finally:
        db.close()


def ensure_user_authz_defaults(db, user: models.User, department_codes: list[str] | None = None) -> None:
    """Voor nieuw aangemaakte gebruikers: koppel (optioneel) afdelingen."""
    codes = department_codes or []
    if not codes:
        default_code = ROLE_TO_DEPARTMENT.get(user.role)
        codes = [default_code] if default_code else []
    first = True
    for code in codes:
        dept = db.query(models.Department).filter(models.Department.code == code).first()
        if dept:
            db.add(models.UserDepartment(user_id=user.id, department_id=dept.id, is_primary=first))
            first = False
    invalidate_permission_cache(user.id)
