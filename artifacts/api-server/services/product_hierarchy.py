"""
ProductHierarchyService (taak #215) — centrale logica voor de canonieke
producthiërarchie: kolomdetectie, staging-import (niet-destructief),
validatie, impactanalyse, apply met wijzigingslog en efficiënte
descendant-queries via het gematerialiseerde pad.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models

logger = logging.getLogger("uvicorn.error")

MAX_LEVELS = 8            # spec vraagt 2–6, we staan tot 8 toe (met warning >6)
WARN_LEVELS = 6
PATH_SEPARATORS = [">", "/", "|", ";", "\\"]

# ── Kolomdetectie ────────────────────────────────────────────────────────────

def detect_mapping(columns: list[str]) -> dict:
    """
    Detecteer kolommen in het bronbestand:
      - option_col: externe optionId-kolom
      - product_col: productcode/SKU-kolom
      - level_cols: expliciete niveau-kolommen (level1/niveau_1/…)
      - path_col: één kolom met het volledige pad (met separator)
    Retourneert een mapping-dict die de gebruiker kan overschrijven.
    """
    cols = [c.strip().lower() for c in columns]
    mapping: dict = {"option_col": None, "product_col": None,
                     "level_cols": [], "path_col": None, "separator": None}

    for c in cols:
        if mapping["option_col"] is None and "option" in c and "id" in c.replace("option", ""):
            mapping["option_col"] = c
        elif mapping["option_col"] is None and c in ("optionid", "option_id", "external_option_id"):
            mapping["option_col"] = c
    for c in cols:
        if c == mapping["option_col"]:
            continue
        if mapping["product_col"] is None and any(
                k in c for k in ("productcode", "product_code", "artikelnummer",
                                 "artikelcode", "sku", "product id", "product_id",
                                 "productid", "drs")):
            mapping["product_col"] = c

    level_cols = []
    for c in cols:
        if c in (mapping["option_col"], mapping["product_col"]):
            continue
        if re.search(r"(level|niveau|laag)[ _-]?\d+", c) or re.fullmatch(r"(hoofdgroep|groep|subgroep|subsubgroep)", c):
            level_cols.append(c)
    if level_cols:
        mapping["level_cols"] = level_cols
    else:
        # één overgebleven kolom met pad-achtige naam of gewoon de rest
        rest = [c for c in cols if c not in (mapping["option_col"], mapping["product_col"])]
        for c in rest:
            if any(k in c for k in ("path", "pad", "hierarchie", "hierarchy", "categor", "boom", "tree")):
                mapping["path_col"] = c
                break
        if mapping["path_col"] is None and len(rest) == 1:
            mapping["path_col"] = rest[0]
    return mapping


def detect_separator(values: list[str]) -> str:
    counts = {sep: 0 for sep in PATH_SEPARATORS}
    for v in values[:200]:
        for sep in PATH_SEPARATORS:
            if sep in (v or ""):
                counts[sep] += 1
    best = max(counts, key=lambda s: counts[s])
    return best if counts[best] > 0 else ">"


def parse_path(row: dict, mapping: dict) -> list[str]:
    if mapping.get("level_cols"):
        parts = [(row.get(c) or "").strip() for c in mapping["level_cols"]]
        # lege tussenniveaus afkappen vanaf het eerste lege niveau
        out = []
        for p in parts:
            if not p:
                break
            out.append(p)
        return out
    col = mapping.get("path_col")
    raw = (row.get(col) or "").strip() if col else ""
    if not raw:
        return []
    sep = mapping.get("separator") or ">"
    return [p.strip() for p in raw.split(sep) if p.strip()]


# ── Staging / validatie ─────────────────────────────────────────────────────

def stage_rows(db: Session, job: models.ImportJob, rows: list[dict], mapping: dict) -> dict:
    """Parkeer alle bestandsrijen in staging; niets raakt de echte hiërarchie."""
    if mapping.get("path_col") and not mapping.get("separator"):
        mapping["separator"] = detect_separator(
            [(r.get(mapping["path_col"]) or "") for r in rows])
    staged = 0
    for i, row in enumerate(rows, start=1):
        row_norm = {k.strip().lower(): (v or "").strip() if isinstance(v, str) else v
                    for k, v in row.items()}
        opt = (row_norm.get(mapping.get("option_col") or "") or "").strip() or None
        code = (row_norm.get(mapping.get("product_col") or "") or "").strip() or None
        path = parse_path(row_norm, mapping)
        db.add(models.ProductHierarchyStagingRow(
            job_id=job.id, row_number=i,
            external_option_id=opt, product_code=code,
            path_names=path, status="nieuw"))
        staged += 1
        if staged % 2000 == 0:
            db.flush()
    db.commit()
    return {"rows_staged": staged, "mapping": mapping}


def validate_job(db: Session, job: models.ImportJob) -> dict:
    """
    Valideer staging-rijen + match producten
    (DRS product-ID/SKU → feed-id → EAN → OEM).
    Zet per rij status/message; retourneert het volledige rapport.
    """
    S = models.ProductHierarchyStagingRow
    P = models.DimProduct
    total_rows = db.query(func.count(S.id)).filter(S.job_id == job.id).scalar() or 0
    rows = (db.query(S).filter(S.job_id == job.id)
            .order_by(S.row_number).yield_per(2000))

    # bestaande producten in bulk ophalen
    codes = {c for (c,) in db.query(S.product_code)
             .filter(S.job_id == job.id, S.product_code.isnot(None)).distinct()}
    sku_set: set[str] = set()
    feed_id_map: dict[str, str] = {}
    ean_map: dict[str, str] = {}
    oem_map: dict[str, str] = {}
    business_map: dict[str, set] = {}
    CHUNK = 5000
    code_list = list(codes)
    # Feed-product-id (raw_attributes.id) — hiërarchie-exports uit PriceShape
    # gebruiken het feed-id als productcode, niet de sku_id/EAN.
    feed_id_expr = P.raw_attributes["id"].as_string()
    for i in range(0, len(code_list), CHUNK):
        chunk = code_list[i:i + CHUNK]
        for (sku,) in db.query(P.sku_id).filter(P.sku_id.in_(chunk)):
            sku_set.add(sku)
        for sku, fid in db.query(P.sku_id, feed_id_expr).filter(feed_id_expr.in_(chunk)):
            if fid is not None:
                key = str(fid)
                feed_id_map[key] = sku if key not in feed_id_map else None
        for sku, ean in db.query(P.sku_id, P.ean).filter(P.ean.in_(chunk)):
            ean_map[ean] = sku if ean not in ean_map else None
        for sku, oem in db.query(P.sku_id, P.oem_code).filter(P.oem_code.in_(chunk)):
            oem_map[oem] = sku if oem not in oem_map else None
        for sku, code in db.query(P.sku_id, P.business_sku).filter(P.business_sku.in_(chunk)):
            business_map.setdefault(code, set()).add(sku)
        for a in db.query(models.ProductSourceAlias).filter(models.ProductSourceAlias.code.in_(chunk)):
            business_map.setdefault(a.code, set()).add(a.sku_id)

    seen_opt: dict[str, int] = {}
    sku_target: dict[str, tuple] = {}   # sku → pad; conflict = fout
    exact_seen: set[tuple] = set()
    counts = {"ontvangen": total_rows, "geldig": 0, "gekoppeld": 0,
              "niet_gevonden": 0, "duplicaten": 0, "fouten": 0}
    warnings: list[str] = []
    errors: list[dict] = []

    for r in rows:
        r.matched_sku_id = None
        r.match_method = None
        path = r.path_names or []
        key = (r.external_option_id, r.product_code, tuple(path))
        if key in exact_seen:
            r.status = "duplicaat"
            r.message = "Exacte duplicaatrij (zelfde optionId, productcode en pad)"
            counts["duplicaten"] += 1
            continue
        exact_seen.add(key)

        if not path:
            r.status = "fout"
            r.message = "Geen hiërarchiepad gevonden in deze rij"
            counts["fouten"] += 1
            errors.append({"rij": r.row_number, "bericht": r.message})
            continue
        if len(path) > MAX_LEVELS:
            r.status = "fout"
            r.message = f"Pad heeft {len(path)} niveaus (maximum {MAX_LEVELS})"
            counts["fouten"] += 1
            errors.append({"rij": r.row_number, "bericht": r.message})
            continue
        if len(path) > WARN_LEVELS and len(warnings) < 20:
            warnings.append(f"Rij {r.row_number}: pad heeft {len(path)} niveaus (>{WARN_LEVELS})")

        if r.external_option_id:
            prev = seen_opt.get(r.external_option_id)
            if prev is not None and prev != tuple(path):
                r.status = "fout"
                r.message = ("optionId komt eerder in het bestand voor met een "
                             "ander pad — conflict")
                counts["fouten"] += 1
                errors.append({"rij": r.row_number, "bericht": r.message})
                continue
            seen_opt[r.external_option_id] = tuple(path)

        # productmatching: DRS product-ID / SKU → feed-id → EAN → OEM
        if r.product_code:
            business_candidates = business_map.get(r.product_code, set())
            if len(business_candidates) > 1:
                r.status = "fout"
                r.message = "Ambigue winkel-/bronartikelcode; expliciete productkoppeling vereist."
                counts["fouten"] += 1
                errors.append({"rij": r.row_number, "bericht": r.message})
                continue
            if len(business_candidates) == 1:
                r.matched_sku_id, r.match_method = next(iter(business_candidates)), "business_sku"
            elif r.product_code in sku_set:
                r.matched_sku_id, r.match_method = r.product_code, "drs_id"
            elif r.product_code in feed_id_map:
                r.matched_sku_id, r.match_method = feed_id_map[r.product_code], "feed_id"
            elif r.product_code in ean_map:
                r.matched_sku_id, r.match_method = ean_map[r.product_code], "ean"
            elif r.product_code in oem_map:
                r.matched_sku_id, r.match_method = oem_map[r.product_code], "oem"
        if r.matched_sku_id:
            prev_target = sku_target.get(r.matched_sku_id)
            if prev_target is not None and prev_target != tuple(path):
                r.status = "fout"
                r.message = ("Product komt eerder in het bestand voor met een "
                             "ander hiërarchiepad — conflict")
                r.matched_sku_id = None
                r.match_method = None
                counts["fouten"] += 1
                errors.append({"rij": r.row_number, "bericht": r.message})
                continue
            sku_target[r.matched_sku_id] = tuple(path)
            counts["gekoppeld"] += 1
        elif r.product_code:
            r.match_method = "geen"
            counts["niet_gevonden"] += 1

        r.status = "geldig"
        r.message = None
        counts["geldig"] += 1

    job.status = "gevalideerd"
    job.rows_processed = counts["geldig"]
    job.rows_failed = counts["fouten"]
    job.rows_duplicates = counts["duplicaten"]
    job.warnings_json = warnings[:50]
    job.error_log = errors[:100]
    db.commit()
    return {"job_id": job.id, "counts": counts, "warnings": warnings[:50],
            "errors": errors[:50],
            # apply is alleen zonder voorbehoud toegestaan als er geen
            # validatiefouten zijn; partial apply vereist expliciete opt-in
            "kan_toepassen": counts["geldig"] > 0 and counts["fouten"] == 0,
            "kan_gedeeltelijk_toepassen": counts["geldig"] > 0 and counts["fouten"] > 0}


# ── Impactanalyse ────────────────────────────────────────────────────────────

def _existing_tree_index(db: Session):
    """Index van bestaande nodes: op (parent_id, naam) en op external_option_id.

    Automatisch afgeleide nodes (feed-categorieën) worden bewust uitgesloten:
    een import mag een auto-node nooit hergebruiken/heractiveren, anders blijft
    de boom deels 'auto' en verliest de import zijn leidende rol.
    """
    from services.hierarchy_autobuild import AUTO_SOURCE
    nodes = (db.query(models.ProductHierarchyNode)
             .filter(models.ProductHierarchyNode.source != AUTO_SOURCE).all())
    by_id = {n.id: n for n in nodes}
    by_parent_name = {(n.parent_id, n.name.lower()): n for n in nodes}
    by_opt = {n.external_option_id: n for n in nodes if n.external_option_id}
    return by_id, by_parent_name, by_opt


def _walk_paths(db: Session, job_id: int):
    """Itereer unieke paden + leaf-optionIds uit geldige staging-rijen."""
    S = models.ProductHierarchyStagingRow
    q = (db.query(S).filter(S.job_id == job_id, S.status == "geldig")
         .order_by(S.row_number))
    seen: set[tuple] = set()
    for r in q.yield_per(2000):
        t = tuple(r.path_names or [])
        key = (t, r.external_option_id)
        if key in seen:
            continue
        seen.add(key)
        yield t, r.external_option_id


def analyze_impact(db: Session, job: models.ImportJob) -> dict:
    by_id, by_parent_name, by_opt = _existing_tree_index(db)
    S = models.ProductHierarchyStagingRow
    A = models.ProductHierarchyAssignment

    new_paths: list[str] = []
    renamed: list[dict] = []
    moved: list[dict] = []
    unchanged = 0
    new_nodes = 0
    leaf_by_opt: dict[str, object] = {}
    leaf_by_path: dict[tuple, object] = {}

    def full_name_path(names: tuple) -> str:
        return " > ".join(names)

    for names, opt in _walk_paths(db, job.id):
        parent = None
        changed = False
        for depth, name in enumerate(names, start=1):
            is_leaf = depth == len(names)
            node = None
            if is_leaf and opt and opt in by_opt:
                node = by_opt[opt]
                if node.name.lower() != name.lower():
                    renamed.append({"option_id": opt, "van": node.name, "naar": name})
                    changed = True
                if node.parent_id != (parent.id if parent else None):
                    moved.append({"option_id": opt, "node": name,
                                  "van": (by_id[node.parent_id].name if node.parent_id in by_id else None),
                                  "naar": (parent.name if parent else None)})
                    changed = True
            else:
                node = by_parent_name.get(((parent.id if parent else None), name.lower()))
            if node is None:
                new_nodes += 1
                changed = True
                # simuleer node zodat diepere niveaus niet dubbel tellen
                class _Sim:  # lichte placeholder
                    def __init__(self, name, parent):
                        self.id = -(len(by_parent_name) + new_nodes)
                        self.name = name
                        self.parent_id = parent.id if parent else None
                node = _Sim(name, parent)
                by_parent_name[((parent.id if parent else None), name.lower())] = node
            parent = node
        if changed:
            new_paths.append(full_name_path(names))
        else:
            unchanged += 1
        if parent is not None:
            leaf_by_path[tuple(names)] = parent
            if opt:
                leaf_by_opt[opt] = parent

    # assignments-impact: zelfde doelresolutie als apply_job
    # (optionId eerst, anders pad), zodat impact en apply overeenstemmen.
    matched = (db.query(S.matched_sku_id, S.external_option_id, S.path_names)
               .filter(S.job_id == job.id, S.status == "geldig",
                       S.matched_sku_id.isnot(None)).all())
    active_assign = {a.sku_id: a for a in db.query(A).filter(A.status == "active")}
    assign_new = assign_moved = assign_unchanged = 0
    seen_sku: set[str] = set()
    for sku, opt, names in matched:
        if sku in seen_sku:
            continue
        seen_sku.add(sku)
        target = leaf_by_opt.get(opt) if opt else None
        if target is None and names:
            target = leaf_by_path.get(tuple(names))
        cur = active_assign.get(sku)
        if cur is None:
            assign_new += 1
        elif target is not None and cur.node_id == getattr(target, "id", None):
            assign_unchanged += 1
        else:
            assign_moved += 1

    unmatched = (db.query(func.count(S.id))
                 .filter(S.job_id == job.id, S.status == "geldig",
                         S.matched_sku_id.is_(None), S.product_code.isnot(None))
                 .scalar() or 0)

    return {
        "job_id": job.id,
        "nodes": {"nieuw": new_nodes, "hernoemd": len(renamed),
                  "verplaatst": len(moved), "ongewijzigde_paden": unchanged},
        "hernoemd_voorbeelden": renamed[:20],
        "verplaatst_voorbeelden": moved[:20],
        "nieuwe_paden_voorbeelden": new_paths[:20],
        "assignments": {"nieuw": assign_new, "verplaatst": assign_moved,
                        "ongewijzigd": assign_unchanged,
                        "niet_gevonden_producten": int(unmatched)},
        "niet_destructief": True,
    }


# ── Apply ────────────────────────────────────────────────────────────────────

def _rebuild_node_path(node: models.ProductHierarchyNode,
                       by_id: dict) -> None:
    parts_ids, parts_names = [], []
    cur = node
    guard = 0
    while cur is not None and guard < 32:
        parts_ids.append(cur.id)
        parts_names.append(cur.name)
        cur = by_id.get(cur.parent_id)
        guard += 1
    parts_ids.reverse()
    parts_names.reverse()
    node.level = len(parts_ids)
    node.path = "/" + "/".join(str(i) for i in parts_ids) + "/"
    node.path_names = " > ".join(parts_names)


def _sync_leaf_paths(db: Session) -> None:
    """
    Synchroniseer de gematerialiseerde padtabel met de actuele boom:
    verwijder rijen voor nodes die geen actief blad (meer) zijn en
    upsert het pad voor elk actief blad. Aantal nodes is begrensd,
    dus dit is een goedkope volledige sync.
    """
    all_nodes = db.query(models.ProductHierarchyNode).all()
    parent_ids = {n.parent_id for n in all_nodes if n.parent_id}
    Ppath = models.ProductHierarchyPath
    existing = {p.leaf_node_id: p for p in db.query(Ppath).all()}
    leaf_ids = set()
    for n in all_nodes:
        if n.id in parent_ids or not n.is_active:
            continue
        leaf_ids.add(n.id)
        node_ids = [int(x) for x in n.path.strip("/").split("/")] if n.path else [n.id]
        row = existing.get(n.id)
        if row is None:
            db.add(Ppath(leaf_node_id=n.id, path_string=n.path_names or n.name,
                         node_ids=node_ids, depth=n.level or 1,
                         external_option_id=n.external_option_id))
        else:
            row.path_string = n.path_names or n.name
            row.node_ids = node_ids
            row.depth = n.level or 1
            row.external_option_id = n.external_option_id
    for leaf_id, row in existing.items():
        if leaf_id not in leaf_ids:
            db.delete(row)


class ManualTreeExists(Exception):
    """De apply is afgebroken omdat er — gecontroleerd ónder de
    hiërarchie-advisory-lock — al een actieve handmatige boom bestaat.
    Gebruikt door de startup-seed (taak #296) om nooit een tweede boom
    over een intussen handmatig geïmporteerde boom heen te zetten."""


def apply_job(db: Session, job: models.ImportJob, username: str,
              deactivate_missing: bool = False,
              require_no_manual_tree: bool = False) -> dict:
    """
    Pas de gevalideerde staging toe. Niet-destructief:
    - nodes worden ge-upsert (nooit verwijderd);
    - hernoemingen/verplaatsingen worden gelogd in de change log;
    - verplaatste producttoewijzingen laten de oude rij als 'superseded' achter;
    - met deactivate_missing=True worden import-nodes die niet meer in het
      bestand voorkomen expliciet gedeactiveerd (gelogd, nooit verwijderd).
    Atomische statusovergang voorkomt dubbele/parallelle applies.
    """
    claimed = (db.query(models.ImportJob)
               .filter(models.ImportJob.id == job.id,
                       models.ImportJob.status == "gevalideerd")
               .update({"status": "bezig"}, synchronize_session=False))
    db.commit()
    if not claimed:
        raise ValueError("Import is al toegepast of wordt al toegepast")
    db.refresh(job)

    # Serialiseer met de autobuild (zelfde advisory lock, blokkerend): een
    # gelijktijdige autobuild die zijn "geen handmatige boom"-controle al
    # deed mag niet meer committen nadat de import de auto-boom retireert.
    # Transactie-gebonden: komt vrij bij de commit/rollback van deze apply.
    from services.hierarchy_autobuild import (
        retire_auto_hierarchy, _ADVISORY_LOCK_KEY,
    )
    from sqlalchemy import text as _sa_text
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(_sa_text("SELECT pg_advisory_xact_lock(:k)"),
                   {"k": _ADVISORY_LOCK_KEY})

    # Precondition-guard voor de startup-seed: pas NA het verkrijgen van de
    # lock controleren of er intussen een actieve handmatige boom is
    # toegepast. Alleen zo is de check atomisch met de apply — een check
    # vóór de lock kan door een parallelle wizard-import worden ingehaald.
    if require_no_manual_tree:
        from services.hierarchy_autobuild import AUTO_SOURCE as _AUTO_SRC
        _manual = (db.query(models.ProductHierarchyNode.id)
                   .filter(models.ProductHierarchyNode.source != _AUTO_SRC,
                           models.ProductHierarchyNode.is_active.is_(True))
                   .first())
        if _manual is not None:
            # Job terug naar 'gevalideerd' zodat de afbraak zichtbaar en
            # herhaalbaar is; de transactie-lock komt vrij bij de commit.
            job.status = "gevalideerd"
            db.commit()
            raise ManualTreeExists(
                "actieve handmatige hiërarchieboom aanwezig — apply "
                "overgeslagen")

    # Handmatige import is leidend: zet een eventueel automatisch afgeleide
    # boom (feed-categorieën) buiten gebruik vóór de import wordt toegepast,
    # zodat de auto-nodes niet als extra roots naast de import blijven staan.
    retired = retire_auto_hierarchy(db, import_job_id=job.id)
    if retired:
        logger.info("Automatische hiërarchie buiten gebruik gesteld "
                    "(%d nodes) — import wordt leidend.", retired)

    by_id, by_parent_name, by_opt = _existing_tree_index(db)
    now = datetime.utcnow()
    log: list[models.ProductHierarchyChangeLog] = []

    def add_log(change_type, node=None, sku=None, old=None, new=None):
        log.append(models.ProductHierarchyChangeLog(
            import_job_id=job.id, node_id=(node.id if node else None),
            sku_id=sku, change_type=change_type, old_value=old, new_value=new,
            source="import", performed_by=username))

    stats = {"nodes_nieuw": 0, "nodes_hernoemd": 0, "nodes_verplaatst": 0,
             "assignments_nieuw": 0, "assignments_verplaatst": 0,
             "assignments_ongewijzigd": 0}
    leaf_by_opt: dict[str, models.ProductHierarchyNode] = {}
    touched: set[int] = set()

    for names, opt in _walk_paths(db, job.id):
        parent = None
        for depth, name in enumerate(names, start=1):
            is_leaf = depth == len(names)
            node = None
            if is_leaf and opt and opt in by_opt:
                node = by_opt[opt]
                if node.name != name:
                    add_log("node_renamed", node=node,
                            old={"name": node.name}, new={"name": name})
                    by_parent_name.pop((node.parent_id, node.name.lower()), None)
                    node.name = name
                    node.updated_by = username
                    stats["nodes_hernoemd"] += 1
                new_parent_id = parent.id if parent else None
                if node.parent_id != new_parent_id:
                    add_log("node_moved", node=node,
                            old={"parent_id": node.parent_id, "path": node.path_names},
                            new={"parent_id": new_parent_id})
                    by_parent_name.pop((node.parent_id, node.name.lower()), None)
                    node.parent_id = new_parent_id
                    node.updated_by = username
                    stats["nodes_verplaatst"] += 1
                by_parent_name[(node.parent_id, node.name.lower())] = node
            else:
                node = by_parent_name.get(((parent.id if parent else None), name.lower()))
            if node is None:
                node = models.ProductHierarchyNode(
                    name=name, parent_id=(parent.id if parent else None),
                    external_option_id=(opt if is_leaf and opt else None),
                    is_active=True, source="import",
                    created_by=username, updated_by=username)
                db.add(node)
                db.flush()   # id nodig voor pad + kinderen
                by_id[node.id] = node
                by_parent_name[(node.parent_id, name.lower())] = node
                if node.external_option_id:
                    by_opt[node.external_option_id] = node
                add_log("node_created", node=node,
                        new={"name": name, "parent_id": node.parent_id,
                             "external_option_id": node.external_option_id})
                stats["nodes_nieuw"] += 1
            elif is_leaf and opt and not node.external_option_id and opt not in by_opt:
                # bestaande node (op naam) krijgt nu zijn externe id
                node.external_option_id = opt
                by_opt[opt] = node
            if not node.is_active:
                node.is_active = True
                node.updated_by = username
                add_log("node_reactivated", node=node, new={"name": node.name})
            touched.add(node.id)
            parent = node
        if opt and parent is not None:
            leaf_by_opt[opt] = parent

    # optioneel: import-nodes die niet meer in het bestand voorkomen deactiveren
    if deactivate_missing:
        stats["nodes_gedeactiveerd"] = 0
        for n in list(by_id.values()):
            if n.id in touched or not n.is_active or n.source != "import":
                continue
            n.is_active = False
            n.valid_to = now
            n.updated_by = username
            add_log("node_deactivated", node=n,
                    old={"name": n.name, "path": n.path_names},
                    new={"is_active": False})
            stats["nodes_gedeactiveerd"] += 1

    # paden herberekenen voor alle nodes en padtabel synchroniseren
    db.flush()
    all_nodes = db.query(models.ProductHierarchyNode).all()
    by_id = {n.id: n for n in all_nodes}
    for n in all_nodes:
        _rebuild_node_path(n, by_id)
    _sync_leaf_paths(db)

    # producttoewijzingen (niet-destructief)
    S = models.ProductHierarchyStagingRow
    A = models.ProductHierarchyAssignment
    active_assign = {a.sku_id: a for a in db.query(A).filter(A.status == "active")}
    matched = (db.query(S.matched_sku_id, S.external_option_id, S.path_names)
               .filter(S.job_id == job.id, S.status == "geldig",
                       S.matched_sku_id.isnot(None)).all())
    seen_sku: set[str] = set()
    for sku, opt, names in matched:
        if sku in seen_sku:
            continue
        seen_sku.add(sku)
        target = leaf_by_opt.get(opt) if opt else None
        if target is None and names:
            # zoek leaf via pad-namen
            parent = None
            for name in names:
                parent = by_parent_name.get(((parent.id if parent else None), name.lower()))
                if parent is None:
                    break
            target = parent
        if target is None:
            continue
        cur = active_assign.get(sku)
        if cur is not None and cur.node_id == target.id:
            stats["assignments_ongewijzigd"] += 1
            continue
        if cur is not None:
            cur.status = "superseded"
            cur.valid_to = now
            add_log("assignment_moved", sku=sku,
                    old={"node_id": cur.node_id},
                    new={"node_id": target.id, "path": target.path_names})
            stats["assignments_verplaatst"] += 1
        else:
            add_log("assignment_created", sku=sku,
                    new={"node_id": target.id, "path": target.path_names})
            stats["assignments_nieuw"] += 1
        newa = A(sku_id=sku, node_id=target.id, status="active",
                 valid_from=now, source="import", assigned_by=username,
                 import_job_id=job.id)
        db.add(newa)
        active_assign[sku] = newa

    for entry in log:
        db.add(entry)
    job.status = "geimporteerd"
    job.completed_at = now
    db.add(models.AuditLog(
        entity_type="product_hierarchy", entity_id=str(job.id),
        action="hierarchy_import_applied", performed_by=username,
        details=f"Hiërarchie-import toegepast (job {job.id})", new_value=stats))
    db.commit()
    return {"job_id": job.id, "stats": stats, "wijzigingen_gelogd": len(log)}


# ── Automatische toewijzing van nieuwe feed-producten ───────────────────────

AUTO_ASSIGN_SOURCE = "auto_import"


def last_applied_import(db: Session) -> models.ImportJob | None:
    """Laatst toegepaste hiërarchie-import (of None)."""
    return (db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy",
                    models.ImportJob.status == "geimporteerd")
            .order_by(models.ImportJob.completed_at.desc()).first())


def auto_assign_new_products(db: Session, sku_ids: list[str] | None = None) -> dict:
    """
    Wijs producten zonder actieve hiërarchie-toewijzing automatisch toe op
    basis van de staging-rijen van de laatst toegepaste Excel-import.

    Bedoeld als post-hook na een feed-sync: de Excel dekt het volledige
    assortiment, dus nieuw binnengekomen feed-producten staan er vrijwel
    altijd al in. Matching volgt dezelfde volgorde als validate_job:
    DRS product-ID/SKU → feed-id (raw_attributes->>'id') → EAN → OEM.

    Niet-destructief: producten met een bestaande actieve toewijzing (hoe dan
    ook ontstaan, dus óók handmatig verplaatste) worden nooit aangeraakt —
    alleen producten ZONDER actieve toewijzing komen in aanmerking.
    Idempotent: een tweede aanroep doet niets meer.
    """
    # Serialiseer met apply/autobuild (zelfde advisory lock, transactie-
    # gebonden) zodat we nooit toewijzen terwijl een import de boom herbouwt.
    # Belangrijk: het lock komt VÓÓR het bepalen van de "laatst toegepaste"
    # import — een apply die intussen bezig was is dan gecommit en wordt hier
    # dus gezien, in plaats van dat we op een verouderde job doorwerken.
    from services.hierarchy_autobuild import _ADVISORY_LOCK_KEY
    from sqlalchemy import text as _sa_text
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(_sa_text("SELECT pg_advisory_xact_lock(:k)"),
                   {"k": _ADVISORY_LOCK_KEY})

    # Racevenster van apply_job afdekken: de apply claimt de job eerst met een
    # commit naar status 'bezig' en neemt pas daarna het lock. Wie in dat
    # venster start, verkrijgt het lock vóór de apply en zou de VORIGE import
    # als "laatste" zien. Zolang er een apply onderweg is ('bezig'), slaan we
    # deze run daarom over — de volgende sync probeert het gewoon opnieuw.
    busy = (db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy",
                    models.ImportJob.status == "bezig").first())
    if busy is not None:
        return {"skipped": True,
                "reason": "hiërarchie-import wordt toegepast (job "
                          f"{busy.id}); volgende sync probeert opnieuw"}

    job = last_applied_import(db)
    if job is None:
        return {"skipped": True, "reason": "geen toegepaste hiërarchie-import"}

    P = models.DimProduct
    A = models.ProductHierarchyAssignment
    S = models.ProductHierarchyStagingRow

    # Producten die in aanmerking komen: zonder actieve toewijzing.
    active_sub = (db.query(A.sku_id)
                  .filter(A.status == "active", A.sku_id == P.sku_id))
    q = db.query(P.sku_id).filter(~active_sub.exists())
    if sku_ids is not None:
        if not sku_ids:
            return {"skipped": True, "reason": "geen kandidaat-producten"}
        q = q.filter(P.sku_id.in_(sku_ids))
    unassigned = {s for (s,) in q.all()}
    if not unassigned:
        return {"toegewezen": 0, "kandidaten": 0, "job_id": job.id}

    # Staging-rij-centrisch, exact zoals validate_job: bouw per productcode
    # lookup-maps over ÁLLE producten (niet alleen ongekoppelde), zodat de
    # matchvolgorde DRS SKU → feed-id → EAN → OEM per rij identiek uitpakt.
    # Een code die de SKU van (al gekoppeld) product A én de EAN van
    # (ongekoppeld) product B is, resolvet dus naar A — en levert géén
    # toewijzing voor B op.
    codes = {c for (c,) in db.query(S.product_code)
             .filter(S.job_id == job.id, S.status == "geldig",
                     S.product_code.isnot(None)).distinct()}
    if not codes:
        return {"toegewezen": 0, "kandidaten": len(unassigned), "job_id": job.id}
    sku_set: set[str] = set()
    feed_id_map: dict[str, str] = {}
    ean_map: dict[str, str] = {}
    oem_map: dict[str, str] = {}
    feed_id_expr = P.raw_attributes["id"].as_string()
    business_map: dict[str, set] = {}
    code_list = list(codes)
    CHUNK = 5000
    for i in range(0, len(code_list), CHUNK):
        chunk = code_list[i:i + CHUNK]
        for (sku,) in db.query(P.sku_id).filter(P.sku_id.in_(chunk)):
            sku_set.add(sku)
        for sku, fid in db.query(P.sku_id, feed_id_expr).filter(feed_id_expr.in_(chunk)):
            if fid is not None:
                key = str(fid)
                feed_id_map[key] = sku if key not in feed_id_map else None
        for sku, ean in db.query(P.sku_id, P.ean).filter(P.ean.in_(chunk)):
            ean_map[ean] = sku if ean not in ean_map else None
        for sku, oem in db.query(P.sku_id, P.oem_code).filter(P.oem_code.in_(chunk)):
            oem_map[oem] = sku if oem not in oem_map else None
        for sku, code in db.query(P.sku_id, P.business_sku).filter(P.business_sku.in_(chunk)):
            business_map.setdefault(code, set()).add(sku)
        for a in db.query(models.ProductSourceAlias).filter(models.ProductSourceAlias.code.in_(chunk)):
            business_map.setdefault(a.code, set()).add(a.sku_id)

    # Resolve elke geldige staging-rij één keer (rijvolgorde = bestandsvolgorde)
    # en verzamel per product het doelpad. Net als bij validate_job wint de
    # éérste rij die naar een product resolvet; een latere rij met een ander
    # pad zou daar 'fout' opleveren en telt hier dus niet mee.
    sku_row: dict[str, tuple[tuple, str | None, str]] = {}  # sku → (pad, opt, methode)
    rows = (db.query(S.product_code, S.path_names, S.external_option_id)
            .filter(S.job_id == job.id, S.status == "geldig",
                    S.product_code.isnot(None), S.path_names.isnot(None))
            .order_by(S.row_number).yield_per(2000))
    for code, names, opt in rows:
        if not names:
            continue
        candidates = business_map.get(code, set())
        if len(candidates) > 1:
            continue
        if len(candidates) == 1:
            sku, method = next(iter(candidates)), "business_sku"
        elif code in sku_set:
            sku, method = code, "drs_id"
        elif code in feed_id_map:
            sku, method = feed_id_map[code], "feed_id"
        elif code in ean_map:
            sku, method = ean_map[code], "ean"
        elif code in oem_map:
            sku, method = oem_map[code], "oem"
        else:
            continue
        if sku not in unassigned or sku in sku_row:
            continue
        sku_row[sku] = (tuple(names), opt, method)

    if not sku_row:
        return {"toegewezen": 0, "kandidaten": len(unassigned), "job_id": job.id}

    by_id, by_parent_name, by_opt = _existing_tree_index(db)

    def resolve_leaf(names: tuple, opt: str | None):
        node = by_opt.get(opt) if opt else None
        if node is None:
            parent = None
            for name in names:
                parent = by_parent_name.get(
                    ((parent.id if parent else None), name.lower()))
                if parent is None:
                    return None
            node = parent
        return node if (node is not None and node.is_active) else None

    now = datetime.utcnow()
    assigned = 0
    for sku, (names, opt, method) in sku_row.items():
        target = resolve_leaf(names, opt)
        if target is None:
            continue
        db.add(A(sku_id=sku, node_id=target.id, status="active",
                 valid_from=now, source=AUTO_ASSIGN_SOURCE,
                 assigned_by="feed-sync", import_job_id=job.id))
        db.add(models.ProductHierarchyChangeLog(
            import_job_id=job.id, sku_id=sku,
            change_type="assignment_created",
            new_value={"node_id": target.id, "path": target.path_names,
                       "match_method": method},
            source=AUTO_ASSIGN_SOURCE, performed_by="feed-sync"))
        assigned += 1
    db.commit()
    if assigned:
        logger.info("Automatische hiërarchie-toewijzing: %d nieuwe producten "
                    "gekoppeld o.b.v. import-job %d.", assigned, job.id)
    return {"toegewezen": assigned, "kandidaten": len(unassigned),
            "job_id": job.id}


# ── Leesqueries ──────────────────────────────────────────────────────────────

def descendant_ids(db: Session, node: models.ProductHierarchyNode) -> list[int]:
    """Alle descendant-node-ids (excl. node zelf) via prefix-LIKE op het pad."""
    N = models.ProductHierarchyNode
    if not node.path:
        return []
    rows = (db.query(N.id).filter(N.path.like(node.path + "%"),
                                  N.id != node.id).all())
    return [r[0] for r in rows]


def node_sku_query(db: Session, node_ids: list[int]):
    A = models.ProductHierarchyAssignment
    return (db.query(A.sku_id)
            .filter(A.node_id.in_(node_ids), A.status == "active"))


def hierarchy_stats(db: Session) -> dict:
    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    P = models.DimProduct
    total_nodes = db.query(func.count(N.id)).scalar() or 0
    active_nodes = db.query(func.count(N.id)).filter(N.is_active == True).scalar() or 0  # noqa: E712
    max_depth = db.query(func.max(N.level)).scalar() or 0
    assigned = (db.query(func.count(func.distinct(A.sku_id)))
                .filter(A.status == "active").scalar() or 0)
    # Verdeling van gekoppelde producten per herkomst (import / auto_import / manual)
    source_rows = (db.query(func.coalesce(A.source, "import"),
                            func.count(func.distinct(A.sku_id)))
                   .filter(A.status == "active")
                   .group_by(func.coalesce(A.source, "import")).all())
    per_source = {"import": 0, AUTO_ASSIGN_SOURCE: 0, "manual": 0}
    for src, cnt in source_rows:
        per_source[src] = per_source.get(src, 0) + int(cnt or 0)
    total_products = db.query(func.count(P.sku_id)).scalar() or 0
    last_import = (db.query(models.ImportJob)
                   .filter(models.ImportJob.upload_type == "product_hierarchy",
                           models.ImportJob.status == "geimporteerd")
                   .order_by(models.ImportJob.completed_at.desc()).first())
    leaf_paths = db.query(func.count(models.ProductHierarchyPath.id)).scalar() or 0
    return {
        "nodes_totaal": total_nodes,
        "nodes_actief": active_nodes,
        "max_diepte": int(max_depth),
        "paden": leaf_paths,
        "producten_totaal": total_products,
        "producten_gekoppeld": assigned,
        "producten_ongekoppeld": max(0, total_products - assigned),
        "gekoppeld_per_bron": per_source,
        "laatste_import": ({
            "job_id": last_import.id,
            "bestand": last_import.filename,
            "voltooid_op": last_import.completed_at.isoformat() if last_import.completed_at else None,
            "door": last_import.uploaded_by,
        } if last_import else None),
    }
