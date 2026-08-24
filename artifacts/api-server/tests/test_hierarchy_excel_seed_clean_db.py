"""
Integratietest voor seed_hierarchy_from_excel() op een schone database
(taak #286).

De bestaande tests in test_hierarchy_excel_seed.py draaien tegen de gedeelde
dev-DB en skippen zodra daar al een handmatige boom staat — precies het
scenario dat in productie bij de eerstvolgende herstart telt (lege DB, geen
bestaande nodes) blijft daardoor ongetest. Deze module bouwt een verse
SQLite-database, wijst seed.SessionLocal daarnaar en draait de volledige
flow (file_to_rows → stage_rows → validate_job → apply_job) end-to-end.

Gecontroleerd wordt:
- ≥6 hoofdcategorie-nodes (actieve import-roots);
- een vooraf aanwezige auto-boom wordt inactief gezet;
- ≥1.000 unieke gematerialiseerde paden;
- idempotentie: een tweede aanroep maakt geen extra job/nodes aan.
"""
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from database import Base
from services.hierarchy_autobuild import AUTO_SOURCE


def _excel_available() -> bool:
    from seed import _excel_hierarchy_path
    return os.path.isfile(_excel_hierarchy_path())


@pytest.fixture()
def clean_session_factory(tmp_path):
    """Verse, lege SQLite-database met het volledige schema."""
    engine = create_engine(f"sqlite:///{tmp_path}/hierarchy_seed.db")
    # ai_feedback heeft een Postgres-only generated TSVECTOR-kolom die
    # SQLite niet kan renderen; die tabel is hier niet nodig.
    Base.metadata.create_all(engine, tables=[
        t for t in Base.metadata.sorted_tables if t.name != "ai_feedback"])
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def _run_seed_against(monkeypatch, factory):
    """Draai seed_hierarchy_from_excel() tegen de opgegeven sessionfactory."""
    import seed as seed_module
    monkeypatch.setattr(seed_module, "SessionLocal", factory)
    monkeypatch.setenv("DISABLE_HIERARCHY_SEED", "false")
    seed_module.seed_hierarchy_from_excel()


@pytest.mark.skipif(not _excel_available(),
                    reason="Excel-hiërarchibestand niet aanwezig in deze omgeving")
def test_seed_full_flow_on_empty_db_and_idempotent(clean_session_factory, monkeypatch):
    factory = clean_session_factory
    db = factory()
    try:
        # Simuleer een productie-DB waar de feed al een auto-boom heeft
        # opgebouwd: die moet na de seed inactief zijn (import is leidend).
        auto_root = models.ProductHierarchyNode(
            name="AutoRoot", parent_id=None, is_active=True,
            source=AUTO_SOURCE, created_by="system", updated_by="system")
        db.add(auto_root)
        db.flush()
        db.add(models.ProductHierarchyNode(
            name="AutoChild", parent_id=auto_root.id, is_active=True,
            source=AUTO_SOURCE, created_by="system", updated_by="system"))
        db.commit()

        # ── Eerste aanroep: volledige import ────────────────────────────
        _run_seed_against(monkeypatch, factory)
        db.expire_all()

        jobs = (db.query(models.ImportJob)
                .filter(models.ImportJob.upload_type == "product_hierarchy")
                .all())
        assert len(jobs) == 1, "Seed moet precies 1 ImportJob aanmaken"
        assert jobs[0].status == "geimporteerd", (
            f"Job-status moet 'geimporteerd' zijn, was: {jobs[0].status}")

        # ≥6 hoofdcategorie-nodes: actieve import-roots.
        root_count = (db.query(models.ProductHierarchyNode)
                      .filter(models.ProductHierarchyNode.parent_id.is_(None),
                              models.ProductHierarchyNode.source == "import",
                              models.ProductHierarchyNode.is_active.is_(True))
                      .count())
        assert root_count >= 6, (
            f"Verwacht ≥6 actieve hoofdcategorie-nodes, gevonden: {root_count}")

        # Auto-boom moet volledig inactief zijn.
        active_auto = (db.query(models.ProductHierarchyNode)
                       .filter(models.ProductHierarchyNode.source == AUTO_SOURCE,
                               models.ProductHierarchyNode.is_active.is_(True))
                       .count())
        assert active_auto == 0, (
            f"Auto-boom moet inactief zijn na de seed, nog actief: {active_auto}")

        # ≥1.000 unieke gematerialiseerde paden.
        path_count = (db.query(models.ProductHierarchyPath.leaf_node_id)
                      .distinct().count())
        assert path_count >= 1000, (
            f"Verwacht ≥1.000 unieke paden, gevonden: {path_count}")

        node_count_first = db.query(models.ProductHierarchyNode).count()

        # ── Tweede aanroep: idempotent, doet niets extra's ───────────────
        _run_seed_against(monkeypatch, factory)
        db.expire_all()

        job_count_after = (db.query(models.ImportJob)
                           .filter(models.ImportJob.upload_type == "product_hierarchy")
                           .count())
        assert job_count_after == 1, (
            "Tweede aanroep mag geen extra ImportJob aanmaken")
        node_count_second = db.query(models.ProductHierarchyNode).count()
        assert node_count_second == node_count_first, (
            "Tweede aanroep mag geen extra nodes aanmaken")
    finally:
        db.close()
