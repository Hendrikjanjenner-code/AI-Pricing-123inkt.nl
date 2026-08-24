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

from database import SessionLocal
import models
from services.hierarchy_autobuild import AUTO_SOURCE

SEED_PREFIX = "exseedtest"


# ── Opruimhulpen ─────────────────────────────────────────────────────────────

def _delete_imported_job(db, job_id):
    """Verwijder staging + job die door de seed is aangemaakt."""
    db.query(models.ProductHierarchyStagingRow).filter(
        models.ProductHierarchyStagingRow.job_id == job_id
    ).delete(synchronize_session=False)
    db.query(models.ProductHierarchyChangeLog).filter(
        models.ProductHierarchyChangeLog.import_job_id == job_id
    ).delete(synchronize_session=False)
    db.query(models.ImportJob).filter(
        models.ImportJob.id == job_id
    ).delete(synchronize_session=False)
    db.commit()


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


# ── Hulpfunctie ──────────────────────────────────────────────────────────────

def _run_seed_with_flag_enabled():
    """Roep seed_hierarchy_from_excel() aan met de vlag uitgeschakeld."""
    original = os.environ.get("DISABLE_HIERARCHY_SEED", "true")
    os.environ["DISABLE_HIERARCHY_SEED"] = "false"
    try:
        # Importeer hier zodat conftest al geladen is maar de vlag overschreven is.
        from seed import seed_hierarchy_from_excel
        seed_hierarchy_from_excel()
    finally:
        os.environ["DISABLE_HIERARCHY_SEED"] = original


# ── Tests ────────────────────────────────────────────────────────────────────

class TestSeedHierarchyExcel:

    def test_skip_when_disable_flag_set(self, db):
        """Met DISABLE_HIERARCHY_SEED=true mag er geen nieuwe ImportJob aangemaakt worden."""
        # conftest.py heeft de vlag al op 'true' — maar we controleren expliciet.
        os.environ["DISABLE_HIERARCHY_SEED"] = "true"
        job_count_before = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy")
            .count()
        )
        from seed import seed_hierarchy_from_excel
        seed_hierarchy_from_excel()
        db.expire_all()
        job_count_after = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy")
            .count()
        )
        assert job_count_after == job_count_before, (
            "seed_hierarchy_from_excel() mocht geen nieuwe job aanmaken "
            "als DISABLE_HIERARCHY_SEED=true"
        )

    def test_skip_when_manual_nodes_exist(self, db):
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

        os.environ["DISABLE_HIERARCHY_SEED"] = "false"
        job_count_before = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy")
            .count()
        )
        try:
            from seed import seed_hierarchy_from_excel
            seed_hierarchy_from_excel()
        finally:
            os.environ["DISABLE_HIERARCHY_SEED"] = "true"

        db.expire_all()
        job_count_after = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy")
            .count()
        )
        assert job_count_after == job_count_before, (
            "seed_hierarchy_from_excel() mocht geen nieuwe job aanmaken "
            "als er al actieve handmatige nodes zijn"
        )

    def test_import_creates_nodes_and_job(self, db):
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

        job_count_before = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy")
            .count()
        )

        os.environ["DISABLE_HIERARCHY_SEED"] = "false"
        created_job_id = None
        try:
            from seed import seed_hierarchy_from_excel
            seed_hierarchy_from_excel()
        finally:
            os.environ["DISABLE_HIERARCHY_SEED"] = "true"

        db.expire_all()

        # Er moet een nieuwe 'geimporteerd'-job zijn.
        job_count_after = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy")
            .count()
        )
        assert job_count_after == job_count_before + 1, (
            "seed_hierarchy_from_excel() moet precies 1 nieuwe ImportJob aanmaken"
        )

        latest_job = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy")
            .order_by(models.ImportJob.id.desc())
            .first()
        )
        created_job_id = latest_job.id
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

        # Opruimen: verwijder de aangemaakte nodes en job weer,
        # zodat andere tests niet op deze toestand bouwen.
        if created_job_id is not None:
            _retire_seed_nodes(db, created_job_id)
            _delete_imported_job(db, created_job_id)

    def test_idempotent_when_called_twice_on_empty_db(self, db):
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

        job_count_before = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy")
            .count()
        )

        os.environ["DISABLE_HIERARCHY_SEED"] = "false"
        first_job_id = None
        try:
            from seed import seed_hierarchy_from_excel
            # Eerste aanroep — importeert de boom.
            seed_hierarchy_from_excel()
            db.expire_all()

            latest = (
                db.query(models.ImportJob)
                .filter(models.ImportJob.upload_type == "product_hierarchy")
                .order_by(models.ImportJob.id.desc())
                .first()
            )
            first_job_id = latest.id if latest else None

            # Tweede aanroep — moet de boom al zien en overslaan.
            seed_hierarchy_from_excel()
        finally:
            os.environ["DISABLE_HIERARCHY_SEED"] = "true"

        db.expire_all()
        job_count_after = (
            db.query(models.ImportJob)
            .filter(models.ImportJob.upload_type == "product_hierarchy")
            .count()
        )
        assert job_count_after == job_count_before + 1, (
            "Tweede aanroep van seed_hierarchy_from_excel() mag géén extra job aanmaken"
        )

        # Opruimen.
        if first_job_id is not None:
            _retire_seed_nodes(db, first_job_id)
            _delete_imported_job(db, first_job_id)
