"""
Automatische producthiërarchie uit feed-categorieën (taak #274).

De globale hiërarchiefilter is pas bruikbaar als er nodes + toewijzingen
bestaan, maar in de praktijk is er vaak (nog) geen handmatige import gedaan
terwijl de feed al categorie/subcategorie per product levert. Deze module
bouwt daarom automatisch een twee-laags hiërarchie op uit
`dim_product.category` / `dim_product.subcategory`:

- Niveau 1: categorie, niveau 2: subcategorie (indien aanwezig).
- Alle automatisch aangemaakte nodes en toewijzingen krijgen
  `source = AUTO_SOURCE`, zodat ze herkenbaar en vervangbaar zijn.
- Een handmatig beheerde of geïmporteerde boom is ALTIJD leidend:
  zodra er ook maar één actieve node met een andere source bestaat, doet
  de autobuild niets. De import-apply ruimt de auto-boom bovendien op
  (zie `retire_auto_hierarchy`).
- Idempotent en incrementeel: bestaande auto-nodes worden hergebruikt,
  nieuwe categorieën uit een latere sync komen erbij, en verplaatste
  producten krijgen — net als bij de import — een `superseded` oude rij
  plus een nieuwe actieve rij (niet-destructief).
- Padtabel-sync is verplicht bij elke boommutatie; deze module hergebruikt
  daarvoor `_rebuild_node_path` en `_sync_leaf_paths` uit de importservice.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

import models
from services.product_hierarchy import _rebuild_node_path, _sync_leaf_paths

logger = logging.getLogger("uvicorn.error")

AUTO_SOURCE = "auto_categorie"
_AUTO_USER = "systeem (feed-categorieën)"
# Vaste advisory-lock-key voor hiërarchie-mutaties (autobuild).
_ADVISORY_LOCK_KEY = 0x68696572  # "hier"


def _clean(value) -> str | None:
    s = str(value).strip() if value is not None else ""
    return s or None


def _load_products(db: Session):
    """
    Producten voor de autobuild. Op Postgres met FOR SHARE-rijlock zodat een
    gelijktijdige feed-apply de rijen niet kan verwijderen tussen deze select
    en onze commit (anders FK-fout op de toewijzing-insert).
    """
    P = models.DimProduct
    q = (db.query(P.sku_id, P.category, P.subcategory)
         .filter(P.is_active.is_(True), P.category.isnot(None),
                 P.category != ""))
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        q = q.with_for_update(read=True)
    return q.all()


def autobuild_hierarchy(db: Session) -> dict:
    """
    Bouw of ververs de automatische hiërarchie uit dim_product-categorieën.

    Retourneert een klein rapport-dict. Doet niets (skipped=True) zodra er
    een handmatig/geïmporteerd beheerde boom bestaat. Fail-safe: elke fout
    (bijv. een FK-race met een gelijktijdige feed-apply die een net gelezen
    product verwijdert) wordt teruggerold zodat de sessie bruikbaar blijft;
    een volgende run herstelt vanzelf.
    """
    try:
        result = _autobuild_inner(db)
        if result.get("skipped"):
            # No-op-paden muteren niets maar hebben wél een transactie geopend
            # (en mogelijk de advisory xact-lock genomen): expliciet afsluiten,
            # anders blijft de lock hangen zolang de sessie leeft en worden
            # álle volgende autobuilds ten onrechte als "bezig" geskipt.
            db.rollback()
        return result
    except Exception:
        logger.warning("Automatische hiërarchie-opbouw teruggerold na fout",
                       exc_info=True)
        db.rollback()
        return {"skipped": True, "reason": "fout tijdens opbouw; teruggerold"}


def _autobuild_inner(db: Session) -> dict:
    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    P = models.DimProduct

    # 0. Serialiseer gelijktijdige autobuilds (startup + feed-sync + import-
    #    apply kunnen samenvallen): transactie-gebonden advisory lock, wordt
    #    automatisch vrijgegeven bij commit/rollback. Alleen op Postgres.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        got = db.execute(
            sa_text("SELECT pg_try_advisory_xact_lock(:k)"),
            {"k": _ADVISORY_LOCK_KEY},
        ).scalar()
        if not got:
            return {"skipped": True,
                    "reason": "andere hiërarchie-opbouw is al bezig"}

    # 1. Handmatige/geïmporteerde boom is leidend — nooit overschrijven.
    foreign = (db.query(N.id)
               .filter(N.source != AUTO_SOURCE, N.is_active.is_(True))
               .first())
    if foreign is not None:
        return {"skipped": True, "reason": "handmatige hiërarchie aanwezig"}

    # 2. Verzamel de actuele (categorie, subcategorie)-combinaties.
    combos = (db.query(P.category, P.subcategory)
              .filter(P.is_active.is_(True), P.category.isnot(None),
                      P.category != "")
              .distinct().all())
    cat_subs: dict[str, set[str]] = {}
    for cat, sub in combos:
        cat_c, sub_c = _clean(cat), _clean(sub)
        if not cat_c:
            continue
        cat_subs.setdefault(cat_c, set())
        if sub_c and sub_c != cat_c:
            cat_subs[cat_c].add(sub_c)
    if not cat_subs:
        return {"skipped": True, "reason": "geen categoriedata in dim_product"}

    # 3. Upsert nodes (hergebruik bestaande auto-nodes op naam+parent).
    auto_nodes = db.query(N).filter(N.source == AUTO_SOURCE).all()
    by_key: dict[tuple[int | None, str], models.ProductHierarchyNode] = {
        (n.parent_id, n.name): n for n in auto_nodes
    }
    created = 0

    def ensure_node(name: str, parent: models.ProductHierarchyNode | None):
        nonlocal created
        key = (parent.id if parent else None, name)
        node = by_key.get(key)
        if node is None:
            node = N(name=name, parent_id=parent.id if parent else None,
                     level=(parent.level + 1) if parent else 1,
                     is_active=True, source=AUTO_SOURCE,
                     created_by=_AUTO_USER, updated_by=_AUTO_USER)
            db.add(node)
            db.flush()  # id nodig voor pad + kinderen
            by_key[key] = node
            created += 1
        elif not node.is_active:
            node.is_active = True
            node.updated_by = _AUTO_USER
        return node

    leaf_for: dict[tuple[str, str | None], models.ProductHierarchyNode] = {}
    ensured_keys: set[tuple[int | None, str]] = set()
    for cat, subs in sorted(cat_subs.items()):
        cat_node = ensure_node(cat, None)
        leaf_for[(cat, None)] = cat_node
        ensured_keys.add((None, cat))
        for sub in sorted(subs):
            leaf_for[(cat, sub)] = ensure_node(sub, cat_node)
            ensured_keys.add((cat_node.id, sub))

    # 3b. Auto-nodes die niet meer uit de actuele feed afleidbaar zijn
    #     deactiveren (nooit verwijderen), zodat verdwenen categorieën niet
    #     selecteerbaar blijven in het filter.
    deactivated = 0
    for key, node in by_key.items():
        if key not in ensured_keys and node.is_active:
            node.is_active = False
            node.updated_by = _AUTO_USER
            deactivated += 1

    # 4. Paden + padtabel volledig hersynchroniseren (verplicht bij mutatie).
    all_nodes = db.query(N).all()
    by_id = {n.id: n for n in all_nodes}
    for n in all_nodes:
        _rebuild_node_path(n, by_id)
    db.flush()
    _sync_leaf_paths(db)

    # 5. Toewijzingen: per product naar de diepste beschikbare node.
    #    Alleen auto-toewijzingen worden beheerd; rijen uit andere bronnen
    #    blijven onaangeroerd (die kunnen hier per definitie niet bestaan
    #    zolang er geen handmatige boom is, maar defensief filteren is
    #    goedkoop). Verplaatsingen: oude rij superseded, nieuwe actieve rij.
    products = _load_products(db)
    active_auto = (db.query(A)
                   .filter(A.source == AUTO_SOURCE, A.status == "active").all())
    current: dict[str, models.ProductHierarchyAssignment] = {}
    for a in active_auto:
        current.setdefault(a.sku_id, a)
    now = datetime.utcnow()
    assigned = moved = 0
    desired_skus: set[str] = set()
    for sku_id, cat, sub in products:
        cat_c, sub_c = _clean(cat), _clean(sub)
        if not cat_c:
            continue
        node = (leaf_for.get((cat_c, sub_c if sub_c != cat_c else None))
                or leaf_for.get((cat_c, None)))
        if node is None:
            continue
        desired_skus.add(sku_id)
        existing = current.get(sku_id)
        if existing is not None and existing.node_id == node.id:
            continue
        if existing is not None:
            existing.status = "superseded"
            existing.valid_to = now
            moved += 1
        db.add(A(sku_id=sku_id, node_id=node.id, is_primary=True,
                 status="active", source=AUTO_SOURCE, assigned_by=_AUTO_USER))
        assigned += 1

    # 5b. Verouderde auto-toewijzingen superseden: producten die inactief
    #     werden, hun categorie verloren of verdwenen mogen niet via het
    #     categoriefilter blijven matchen. Niet-destructief (rij blijft).
    stale = 0
    for sku_id, a in current.items():
        if sku_id not in desired_skus and a.status == "active":
            a.status = "superseded"
            a.valid_to = now
            stale += 1

    db.commit()
    report = {"skipped": False, "nodes_created": created,
              "nodes_deactivated": deactivated,
              "assignments_written": assigned, "assignments_moved": moved,
              "assignments_retired": stale,
              "categories": len(cat_subs)}
    if created or assigned or moved or deactivated or stale:
        logger.info("Automatische hiërarchie bijgewerkt: %s", report)
    return report


def retire_auto_hierarchy(db: Session, import_job_id: int | None = None) -> int:
    """
    Zet de automatisch afgeleide boom buiten gebruik zodra een handmatige
    import wordt toegepast: auto-nodes gedeactiveerd, actieve
    auto-toewijzingen superseded. Verwijdert niets (niet-destructief).
    Retourneert het aantal gedeactiveerde nodes. De aanroeper commit.
    """
    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    now = datetime.utcnow()
    nodes = db.query(N).filter(N.source == AUTO_SOURCE,
                               N.is_active.is_(True)).all()
    for n in nodes:
        n.is_active = False
        n.updated_by = _AUTO_USER
    (db.query(A)
     .filter(A.source == AUTO_SOURCE, A.status == "active")
     .update({A.status: "superseded", A.valid_to: now,
              A.import_job_id: import_job_id}, synchronize_session=False))
    return len(nodes)
