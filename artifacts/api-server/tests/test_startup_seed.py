"""
Taak #296 — de zware hiërarchie-seed mag de startup niet blokkeren en moet
in testomgevingen (DISABLE_HIERARCHY_SEED) volledig worden overgeslagen,
inclusief de autobuild-fallback.
"""
import os

from fastapi.testclient import TestClient

from main import app, startup_state
from seed import seed_hierarchy_from_excel


def test_healthz_toont_seed_status_skipped_in_tests():
    # conftest zet DISABLE_HIERARCHY_SEED: er wordt géén achtergrondseed
    # gepland en /api/healthz rapporteert dat expliciet.
    assert os.environ.get("DISABLE_HIERARCHY_SEED", "").lower() in ("1", "true", "yes")
    with TestClient(app) as client:
        r = client.get("/api/healthz")
        assert r.status_code == 200
        seed_info = r.json().get("hierarchy_seed")
        assert seed_info is not None
        assert seed_info["status"] == "skipped"
        assert seed_info["error"] is None
        assert startup_state["hierarchy_seed_status"] == "skipped"


def test_seed_functie_respecteert_disable_vlag():
    # De seed retourneert een expliciete status en muteert niets.
    assert seed_hierarchy_from_excel() == "disabled"


def test_apply_guard_breekt_af_bij_handmatige_boom():
    """Regressie (taak #296): verschijnt er een handmatige boom tussen
    staging en apply, dan breekt apply_job met require_no_manual_tree af
    ónder de hiërarchie-lock en wordt er niets toegepast."""
    from datetime import datetime

    import models
    from database import SessionLocal
    from engine.import_engine import new_batch_id
    from services import product_hierarchy as svc

    UNIEK = "ZZTest-SeedGuard-Cat-296"
    db = SessionLocal()
    job = None
    manual_node_id = None
    try:
        job = models.ImportJob(
            upload_type="product_hierarchy", filename="guard.xlsx",
            status="nieuw", uploaded_by="test", source="Handmatig",
            file_type="xlsx", batch_id=new_batch_id(),
            created_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        rows = [{"Level 1": UNIEK}]
        mapping = svc.detect_mapping(list(rows[0].keys()))
        svc.stage_rows(db, job, rows, mapping)
        result = svc.validate_job(db, job)
        assert result.get("kan_toepassen") or result.get("kan_gedeeltelijk_toepassen")

        # "Parallelle" handmatige import commit tussen staging en apply.
        manual = models.ProductHierarchyNode(
            name=UNIEK + "-manueel", level=1, source="import",
            is_active=True, path_names=UNIEK + "-manueel",
        )
        db.add(manual)
        db.commit()
        manual_node_id = manual.id

        try:
            svc.apply_job(db, job, username="test",
                          require_no_manual_tree=True)
            raise AssertionError("apply_job had ManualTreeExists moeten geven")
        except svc.ManualTreeExists:
            pass
        db.rollback()

        # Niets toegepast; job weer 'gevalideerd' (herhaalbaar).
        assert (db.query(models.ProductHierarchyNode)
                .filter(models.ProductHierarchyNode.name == UNIEK)
                .first()) is None
        db.refresh(job)
        assert job.status == "gevalideerd"
    finally:
        db.rollback()
        if manual_node_id is not None:
            db.query(models.ProductHierarchyNode).filter(
                models.ProductHierarchyNode.id == manual_node_id
            ).delete(synchronize_session=False)
        if job is not None:
            db.query(models.ProductHierarchyStagingRow).filter(
                models.ProductHierarchyStagingRow.job_id == job.id
            ).delete(synchronize_session=False)
            db.query(models.ProductHierarchyChangeLog).filter(
                models.ProductHierarchyChangeLog.import_job_id == job.id
            ).delete(synchronize_session=False)
            db.query(models.ImportJob).filter(
                models.ImportJob.id == job.id
            ).delete(synchronize_session=False)
        db.commit()
        db.close()
