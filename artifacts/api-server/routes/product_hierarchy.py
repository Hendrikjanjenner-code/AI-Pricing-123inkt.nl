"""
Canonieke producthiërarchie (taak #215) — REST API.

Import-wizard (niet-destructief, staged):
  POST /api/product-hierarchy/import/upload      → staging + kolomdetectie + preview
  POST /api/product-hierarchy/import/{id}/validate
  GET  /api/product-hierarchy/import/{id}/impact
  POST /api/product-hierarchy/import/{id}/apply
  GET  /api/product-hierarchy/import/{id}

Leesqueries (ProductHierarchyService):
  tree / children / descendants / ancestors / breadcrumb / products / search /
  stats / changes.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import auth as auth_utils
import models
from database import get_db
from engine.import_engine import file_to_rows, new_batch_id
from services import product_hierarchy as svc

router = APIRouter(prefix="/api/product-hierarchy", tags=["product-hierarchy"])

MUTATE_ROLES = ("admin", "pricing_manager")


def _get_job(db: Session, job_id: int) -> models.ImportJob:
    job = (db.query(models.ImportJob)
           .filter(models.ImportJob.id == job_id,
                   models.ImportJob.upload_type == "product_hierarchy").first())
    if job is None:
        raise HTTPException(status_code=404, detail="Importtaak niet gevonden")
    return job


def _get_node(db: Session, node_id: int) -> models.ProductHierarchyNode:
    node = db.query(models.ProductHierarchyNode).filter(
        models.ProductHierarchyNode.id == node_id).first()
    if node is None:
        raise HTTPException(status_code=404, detail="Hiërarchie-node niet gevonden")
    return node


def _node_dict(n: models.ProductHierarchyNode, sku_count: int | None = None) -> dict:
    d = {
        "id": n.id, "name": n.name, "parent_id": n.parent_id,
        "level": n.level, "path": n.path, "path_names": n.path_names,
        "external_option_id": n.external_option_id,
        "is_active": n.is_active, "source": n.source,
        "valid_from": n.valid_from.isoformat() if n.valid_from else None,
        "valid_to": n.valid_to.isoformat() if n.valid_to else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }
    if sku_count is not None:
        d["sku_count"] = sku_count
    return d


# ── Import-wizard ────────────────────────────────────────────────────────────

@router.post("/import/upload")
async def upload_hierarchy_file(
    file: UploadFile = File(...),
    mapping_json: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*MUTATE_ROLES)),
):
    """Stap 1: bestand → staging. Er verandert niets aan de echte hiërarchie."""
    fname = file.filename or "hierarchie.xlsx"
    file_ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "csv"
    content = await file.read()
    warnings: list = []
    try:
        rows = file_to_rows(content, fname, warnings)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bestand kon niet worden ingelezen: {e}")
    if not rows:
        raise HTTPException(status_code=400, detail="Bestand bevat geen datarijen")

    mapping = None
    if mapping_json:
        import json
        try:
            mapping = json.loads(mapping_json)
        except ValueError:
            raise HTTPException(status_code=400, detail="mapping_json is geen geldige JSON")
    detected = svc.detect_mapping(list(rows[0].keys()))
    if mapping:
        detected.update({k: v for k, v in mapping.items() if v})
    if not detected.get("level_cols") and not detected.get("path_col"):
        raise HTTPException(
            status_code=400,
            detail="Geen hiërarchiekolommen herkend; geef een mapping op "
                   "(level_cols of path_col)")

    job = models.ImportJob(
        upload_type="product_hierarchy", filename=fname, status="concept",
        uploaded_by=current_user.username, source="Handmatig",
        file_type=file_ext, batch_id=new_batch_id(),
        import_mode="updaten", warnings_json=warnings[:50])
    db.add(job)
    db.commit()
    db.refresh(job)

    result = svc.stage_rows(db, job, rows, detected)
    preview = [
        {"row_number": r.row_number, "external_option_id": r.external_option_id,
         "product_code": r.product_code, "path": r.path_names}
        for r in db.query(models.ProductHierarchyStagingRow)
        .filter(models.ProductHierarchyStagingRow.job_id == job.id)
        .order_by(models.ProductHierarchyStagingRow.row_number).limit(10)
    ]
    return {"job_id": job.id, "batch_id": job.batch_id,
            "rows_staged": result["rows_staged"], "mapping": result["mapping"],
            "kolommen": list(rows[0].keys()), "preview": preview,
            "warnings": warnings[:50], "status": job.status}


@router.post("/import/{job_id}/validate")
def validate_import(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*MUTATE_ROLES)),
):
    job = _get_job(db, job_id)
    if job.status not in ("concept", "gevalideerd"):
        raise HTTPException(status_code=409,
                            detail=f"Importtaak heeft status '{job.status}' en kan niet opnieuw gevalideerd worden")
    return svc.validate_job(db, job)


@router.get("/import/{job_id}/impact")
def import_impact(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    job = _get_job(db, job_id)
    if job.status not in ("gevalideerd", "geimporteerd"):
        raise HTTPException(status_code=409, detail="Valideer de import eerst")
    return svc.analyze_impact(db, job)


@router.post("/import/{job_id}/apply")
def apply_import(
    job_id: int,
    deactivate_missing: bool = Query(
        False, description="Deactiveer import-nodes die niet meer in het bestand voorkomen (expliciete opt-in; nodes worden nooit verwijderd)"),
    force_partial: bool = Query(
        False, description="Pas alleen de geldige rijen toe ondanks validatiefouten (expliciete opt-in; foutrijen worden overgeslagen en blijven in het rapport)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role(*MUTATE_ROLES)),
):
    job = _get_job(db, job_id)
    if job.status == "geimporteerd":
        raise HTTPException(status_code=409, detail="Deze import is al toegepast")
    if job.status != "gevalideerd":
        raise HTTPException(status_code=409, detail="Valideer de import eerst")
    if (job.rows_failed or 0) > 0 and not force_partial:
        raise HTTPException(
            status_code=409,
            detail=f"Import bevat {job.rows_failed} validatiefout(en); los deze op "
                   "of pas expliciet gedeeltelijk toe met force_partial=true")
    try:
        return svc.apply_job(db, job, current_user.username,
                             deactivate_missing=deactivate_missing)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        db.rollback()
        job.status = "fout"
        job.error_message = str(e)[:1000]
        db.commit()
        raise HTTPException(status_code=500, detail=f"Import toepassen mislukt: {e}")


@router.get("/import/{job_id}")
def import_status(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    job = _get_job(db, job_id)
    S = models.ProductHierarchyStagingRow
    per_status = dict(db.query(S.status, func.count(S.id))
                      .filter(S.job_id == job.id).group_by(S.status).all())
    return {
        "job_id": job.id, "status": job.status, "filename": job.filename,
        "uploaded_by": job.uploaded_by,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "rows_processed": job.rows_processed, "rows_failed": job.rows_failed,
        "rows_duplicates": job.rows_duplicates or 0,
        "staging_per_status": per_status,
        "warnings": job.warnings_json or [], "error_log": job.error_log or [],
        "error_message": job.error_message,
    }


@router.get("/imports")
def list_imports(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    jobs = (db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy")
            .order_by(models.ImportJob.created_at.desc()).limit(limit).all())
    return [{
        "job_id": j.id, "status": j.status, "filename": j.filename,
        "uploaded_by": j.uploaded_by,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        "rows_processed": j.rows_processed, "rows_failed": j.rows_failed,
        "rows_duplicates": j.rows_duplicates or 0,
    } for j in jobs]


# ── Leesqueries ──────────────────────────────────────────────────────────────

@router.get("/stats")
def stats(db: Session = Depends(get_db),
          current_user: models.User = Depends(auth_utils.get_current_user)):
    return svc.hierarchy_stats(db)


@router.get("/tree")
def tree(
    root_id: int | None = Query(None),
    depth: int = Query(2, ge=1, le=8),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    """Boom vanaf root (of een node), beperkt tot `depth` niveaus (lazy load)."""
    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    if root_id is not None:
        root = _get_node(db, root_id)
        base_level = root.level or 1
        q = db.query(N).filter(N.path.like((root.path or "") + "%"),
                               N.level <= base_level + depth)
    else:
        q = db.query(N).filter(N.level <= depth)
    if not include_inactive:
        q = q.filter(N.is_active == True)  # noqa: E712
    nodes = q.order_by(N.level, N.name).all()

    counts = dict(db.query(A.node_id, func.count(A.id))
                  .filter(A.status == "active").group_by(A.node_id).all())
    # parent-ids over de hele tabel, zodat has_children ook klopt voor de
    # diepste geladen laag (lazy load in de UI)
    all_parent_ids = {pid for (pid,) in db.query(N.parent_id)
                      .filter(N.parent_id.isnot(None)).distinct()}
    by_parent: dict = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)

    def build(n):
        d = _node_dict(n, sku_count=counts.get(n.id, 0))
        d["children"] = [build(c) for c in by_parent.get(n.id, [])]
        d["has_children"] = n.id in all_parent_ids
        return d

    if root_id is not None:
        return build(root)
    roots = by_parent.get(None, [])
    return {"roots": [build(r) for r in roots], "totaal_geladen": len(nodes)}


@router.get("/nodes/{node_id}")
def node_detail(node_id: int, db: Session = Depends(get_db),
                current_user: models.User = Depends(auth_utils.get_current_user)):
    node = _get_node(db, node_id)
    A = models.ProductHierarchyAssignment
    direct = db.query(func.count(A.id)).filter(
        A.node_id == node.id, A.status == "active").scalar() or 0
    desc = svc.descendant_ids(db, node)
    total = direct
    if desc:
        total += db.query(func.count(A.id)).filter(
            A.node_id.in_(desc), A.status == "active").scalar() or 0
    d = _node_dict(node, sku_count=direct)
    d["sku_count_incl_descendants"] = total
    d["descendant_count"] = len(desc)
    return d


@router.get("/nodes/{node_id}/children")
def node_children(node_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(auth_utils.get_current_user)):
    node = _get_node(db, node_id)
    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    children = (db.query(N).filter(N.parent_id == node.id)
                .order_by(N.name).all())
    counts = dict(db.query(A.node_id, func.count(A.id))
                  .filter(A.status == "active",
                          A.node_id.in_([c.id for c in children] or [0]))
                  .group_by(A.node_id).all())
    return [_node_dict(c, sku_count=counts.get(c.id, 0)) for c in children]


@router.get("/nodes/{node_id}/descendants")
def node_descendants(node_id: int,
                     limit: int = Query(500, ge=1, le=5000),
                     db: Session = Depends(get_db),
                     current_user: models.User = Depends(auth_utils.get_current_user)):
    node = _get_node(db, node_id)
    ids = svc.descendant_ids(db, node)
    N = models.ProductHierarchyNode
    nodes = (db.query(N).filter(N.id.in_(ids or [0]))
             .order_by(N.level, N.name).limit(limit).all())
    return {"node_id": node.id, "descendant_ids": ids,
            "descendants": [_node_dict(n) for n in nodes],
            "totaal": len(ids)}


@router.get("/nodes/{node_id}/ancestors")
@router.get("/nodes/{node_id}/breadcrumb")
def node_ancestors(node_id: int, db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth_utils.get_current_user)):
    node = _get_node(db, node_id)
    N = models.ProductHierarchyNode
    ids = [int(x) for x in (node.path or "").strip("/").split("/") if x]
    nodes = db.query(N).filter(N.id.in_(ids or [0])).all()
    order = {nid: i for i, nid in enumerate(ids)}
    nodes.sort(key=lambda n: order.get(n.id, 0))
    return {"breadcrumb": [_node_dict(n) for n in nodes]}


@router.get("/nodes/{node_id}/products")
def node_products(node_id: int,
                  include_descendants: bool = Query(True),
                  q: str | None = Query(None),
                  limit: int = Query(50, ge=1, le=500),
                  offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db),
                  current_user: models.User = Depends(auth_utils.get_current_user)):
    node = _get_node(db, node_id)
    ids = [node.id]
    if include_descendants:
        ids += svc.descendant_ids(db, node)
    A = models.ProductHierarchyAssignment
    P = models.DimProduct
    query = (db.query(P, A.node_id).join(A, A.sku_id == P.sku_id)
             .filter(A.node_id.in_(ids), A.status == "active"))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(P.sku_id.ilike(like), P.product_name.ilike(like),
                                 P.brand.ilike(like), P.ean.ilike(like)))
    total = query.count()
    rows = query.order_by(P.sku_id).offset(offset).limit(limit).all()
    return {
        "node_id": node.id, "totaal": total, "limit": limit, "offset": offset,
        "producten": [{
            "sku_id": p.sku_id, "product_name": p.product_name,
            "brand": p.brand, "ean": p.ean,
            "current_price": float(p.current_price) if p.current_price is not None else None,
            "node_id": nid,
        } for p, nid in rows],
    }


@router.get("/search")
def search(q: str = Query(..., min_length=1),
           limit: int = Query(20, ge=1, le=100),
           db: Session = Depends(get_db),
           current_user: models.User = Depends(auth_utils.get_current_user)):
    N = models.ProductHierarchyNode
    like = f"%{q}%"
    nodes = (db.query(N)
             .filter(or_(N.name.ilike(like), N.path_names.ilike(like),
                         N.external_option_id.ilike(like)))
             .order_by(N.level, N.name).limit(limit).all())
    return [_node_dict(n) for n in nodes]


@router.get("/changes")
def changes(node_id: int | None = Query(None),
            limit: int = Query(50, ge=1, le=500),
            db: Session = Depends(get_db),
            current_user: models.User = Depends(auth_utils.get_current_user)):
    C = models.ProductHierarchyChangeLog
    q = db.query(C)
    if node_id is not None:
        q = q.filter(C.node_id == node_id)
    rows = q.order_by(C.created_at.desc(), C.id.desc()).limit(limit).all()
    return [{
        "id": c.id, "change_type": c.change_type, "node_id": c.node_id,
        "sku_id": c.sku_id, "old_value": c.old_value, "new_value": c.new_value,
        "source": c.source, "performed_by": c.performed_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "import_job_id": c.import_job_id,
    } for c in rows]


# ── Node-mutaties (alleen bevoegde rollen) ──────────────────────────────────

class NodePatch(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    is_active: bool | None = None


@router.patch("/nodes/{node_id}")
def patch_node(node_id: int, body: NodePatch,
               db: Session = Depends(get_db),
               current_user: models.User = Depends(auth_utils.require_role(*MUTATE_ROLES))):
    node = _get_node(db, node_id)
    C = models.ProductHierarchyChangeLog
    changed = False
    if body.name is not None and body.name.strip() and body.name != node.name:
        db.add(C(node_id=node.id, change_type="node_renamed", source="handmatig",
                 old_value={"name": node.name}, new_value={"name": body.name.strip()},
                 performed_by=current_user.username))
        node.name = body.name.strip()
        changed = True
    if body.parent_id is not None and body.parent_id != node.parent_id:
        if body.parent_id == node.id:
            raise HTTPException(status_code=400, detail="Node kan niet zijn eigen parent zijn")
        parent = _get_node(db, body.parent_id)
        if parent.path and node.path and parent.path.startswith(node.path):
            raise HTTPException(status_code=400,
                                detail="Node kan niet onder zijn eigen subtree worden gehangen")
        db.add(C(node_id=node.id, change_type="node_moved", source="handmatig",
                 old_value={"parent_id": node.parent_id},
                 new_value={"parent_id": body.parent_id},
                 performed_by=current_user.username))
        node.parent_id = body.parent_id
        changed = True
    if body.is_active is not None and body.is_active != node.is_active:
        db.add(C(node_id=node.id,
                 change_type="node_reactivated" if body.is_active else "node_deactivated",
                 source="handmatig", old_value={"is_active": node.is_active},
                 new_value={"is_active": body.is_active},
                 performed_by=current_user.username))
        node.is_active = body.is_active
        changed = True
    if changed:
        node.updated_by = current_user.username
        db.flush()
        all_nodes = db.query(models.ProductHierarchyNode).all()
        by_id = {n.id: n for n in all_nodes}
        for n in all_nodes:
            svc._rebuild_node_path(n, by_id)
        svc._sync_leaf_paths(db)
        db.commit()
    return _node_dict(node)
