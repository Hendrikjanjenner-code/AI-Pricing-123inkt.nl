"""
Tests voor seed_hierarchy_from_excel() (taak #281).

Dekt:
- skip wanneer DISABLE_HIERARCHY_SEED=true is gezet;
- skip wanneer er al actieve handmatige nodes aanwezig zijn;
- volledige import op een schone (auto-only of lege) database;
- idempotentie: tweede aanroep doet niets extra's.

Let op: deze module overschrijft DISABLE_HIERARCHY_SEED tijdelijk naar 'false'
om de import-logica te testen. conftest.py zet hem op 'true' om interferentie
met andere testmodules te voorkomen.
"""
import os
import pytest

from conftest import (
    purge_hierarchy_import_jobs_by_ids, register_hierarchy_test_job_ids,
)
from database import SessionLocal
import models
from services.hierarchy_autobuild import AUTO_SOURCE

SEED_PREFIX = "exseedtest"


# ── Opruimhulpen ─────────────────────────────────────────────────────────────

def _retire_seed_nodes(db, job_id: int):
    """
    Zet nodes die door de seed zijn aangemaakt op is_active=False en verwijder
    hun assignments/paths zodat de DB-toestand van vóór de test hersteld wordt.
    Gebruikt de job_id om enkel de seed-nodes te targeten.
    """
    log_entries = (
        db.query(models.ProductHierarchyChangeLog.node_id)
        .filter(
            models.ProductHierarchyChangeLog.import_job_id == job_id,
            models.ProductHierarchyChangeLog.node_id.isnot(None),
        )
        .distinct()
        .all()
    )
    node_ids = [r.node_id for r in log_entries]

    # Assignments van deze seed-nodes verwijderen.
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
        db.commit()

    # Alle seed-nodes die níet in de changelog staan (roots etc.) ook weg.
    # Gebruik source="import" + batch_id van de job.
    job = db.query(models.ImportJob).filter(models.ImportJob.id == job_id).first()
    if job:
        batch = job.batch_id
        if batch:
            db.query(models.ProductHierarchyNode).filter(
                models.ProductHierarchyNode.source == "import"
            ).delete(synchronize_session=False)
            db.commit()


# ── Fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db(hierarchy_suite_lock):
    session = SessionLocal()
    yield session
    session.close()


# ── Getrackte seed-run met gegarandeerde opruiming ───────────────────────────

@pytest.fixture()
def run_seed(db):
    """
    Voer seed_hierarchy_from_excel() uit en houd bij welke ImportJobs erdoor
    ontstaan. Nieuwe job-ids worden direct (vóór enige assert) geregistreerd
    voor de suite-brede residu-check, en de teardown ruimt ze gegarandeerd op
    — óók als een assert halverwege faalt. Een achtergebleven seed-job met
    status "geimporteerd" zou anders de echte Excel-import maskeren als
    "laatst toegepaste import" (incident 25-08).
    """
    created: list[int] = []

    def _run(flag: str = "false") -> list[int]:
        before = {j for (j,) in db.query(models.ImportJob.id).filter(
            models.ImportJob.upload_type == "product_hierarchy")}
        original = os.environ.get("DISABLE_HIERARCHY_SEED", "true")
        os.environ["DISABLE_HIERARCHY_SEED"] = flag
        try:
            from seed import seed_hierarchy_from_excel
            seed_hierarchy_from_excel()
        finally:
            os.environ["DISABLE_HIERARCHY_SEED"] = original
        db.expire_all()
        new_ids = [j for (j,) in db.query(models.ImportJob.id).filter(
            models.ImportJob.upload_type == "product_hierarchy")
            if j not in before]
        created.extend(new_ids)
        register_hierarchy_test_job_ids(new_ids)
        return new_ids

    yield _run

    db.rollback()
    for jid in created:
        _retire_seed_nodes(db, jid)
    purge_hierarchy_import_jobs_by_ids(db, created)
    db.commit()


# ── Tests ────────────────────────────────────────────────────────────────────

class TestSeedHierarchyExcel:

    def test_skip_when_disable_flag_set(self, db, run_seed):
        """Met DISABLE_HIERARCHY_SEED=true mag er geen nieuwe ImportJob aangemaakt worden."""
        new_ids = run_seed(flag="true")
        assert new_ids == [], (
            "seed_hierarchy_from_excel() mocht geen nieuwe job aanmaken "
            "als DISABLE_HIERARCHY_SEED=true"
        )

    def test_skip_when_manual_nodes_exist(self, db, run_seed):
        """Als er al actieve handmatige nodes zijn, wordt de seed overgeslagen."""
        # Controleer of er al handmatige nodes zijn (productie/dev kunnen ze hebben).
        existing = (
            db.query(models.ProductHierarchyNode.id)
            .filter(
                models.ProductHierarchyNode.source != AUTO_SOURCE,
                models.ProductHierarchyNode.is_active.is_(True),
            )
            .first()
        )
        if existing is None:
            pytest.skip(
                "Geen handmatige nodes aanwezig — "
                "idempotentie-skip kan alleen getest worden als de boom al bestaat."
            )

        new_ids = run_seed()
        assert new_ids == [], (
            "seed_hierarchy_from_excel() mocht geen nieuwe job aanmaken "
            "als er al actieve handmatige nodes zijn"
        )

    def test_import_creates_nodes_and_job(self, db, run_seed):
        """
        Op een database zonder actieve handmatige nodes importeert de seed
        de Excel-boom correct: er komen nodes en een 'geimporteerd'-job.
        """
        # Skip als de database al een handmatige boom heeft (gedeelde dev-DB).
        existing_node = (
            db.query(models.ProductHierarchyNode.id)
            .filter(
                models.ProductHierarchyNode.source != AUTO_SOURCE,
                models.ProductHierarchyNode.is_active.is_(True),
            )
            .first()
        )
        if existing_node is not None:
            pytest.skip(
                "Handmatige boom al aanwezig — volledige import-test vereist "
                "een schone database."
            )

        excel_path = None
        try:
            from seed import _excel_hierarchy_path
            excel_path = _excel_hierarchy_path()
        except Exception:
            pass
        if excel_path is None or not os.path.isfile(excel_path):
            pytest.skip("Excel-bestand niet aanwezig in deze omgeving.")

        new_ids = run_seed()

        # Er moet precies één nieuwe 'geimporteerd'-job zijn.
        assert len(new_ids) == 1, (
            "seed_hierarchy_from_excel() moet precies 1 nieuwe ImportJob aanmaken"
        )
        latest_job = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.id == new_ids[0])
            .one()
        )
        assert latest_job.status == "geimporteerd", (
            f"Job-status moet 'geimporteerd' zijn, was: {latest_job.status}"
        )

        # Er moeten actieve import-nodes zijn.
        node_count = (
            db.query(models.ProductHierarchyNode)
            .filter(
                models.ProductHierarchyNode.source != AUTO_SOURCE,
                models.ProductHierarchyNode.is_active.is_(True),
            )
            .count()
        )
        assert node_count > 0, (
            "Na seed_hierarchy_from_excel() moeten er actieve handmatige nodes zijn"
        )
        # Opruimen gebeurt gegarandeerd in de run_seed-teardown.

    def test_idempotent_when_called_twice_on_empty_db(self, db, run_seed):
        """
        Twee opeenvolgende aanroepen op een schone DB mogen maar 1 job produceren.
        De tweede aanroep detecteert de actieve handmatige nodes en slaat over.
        """
        existing_node = (
            db.query(models.ProductHierarchyNode.id)
            .filter(
                models.ProductHierarchyNode.source != AUTO_SOURCE,
                models.ProductHierarchyNode.is_active.is_(True),
            )
            .first()
        )
        if existing_node is not None:
            pytest.skip(
                "Handmatige boom al aanwezig — idempotentie-test vereist "
                "een schone database."
            )

        excel_path = None
        try:
            from seed import _excel_hierarchy_path
            excel_path = _excel_hierarchy_path()
        except Exception:
            pass
        if excel_path is None or not os.path.isfile(excel_path):
            pytest.skip("Excel-bestand niet aanwezig in deze omgeving.")

        # Eerste aanroep — importeert de boom.
        first_ids = run_seed()
        assert len(first_ids) == 1

        # Tweede aanroep — moet de boom al zien en overslaan.
        second_ids = run_seed()
        assert second_ids == [], (
            "Tweede aanroep van seed_hierarchy_from_excel() mag géén extra job aanmaken"
        )
        # Opruimen gebeurt gegarandeerd in de run_seed-teardown.
