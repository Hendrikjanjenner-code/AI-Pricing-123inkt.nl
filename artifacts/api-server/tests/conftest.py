"""
Gedeelde testconfiguratie: schakel alle achtergrond-schedulers uit tijdens
testruns. Een volledige suite-run duurt langer dan de opstartvertragingen van
de schedulers (feed-sync, DQ-scan, AI-budgetopruiming, AI-sleutelmonitor);
zonder deze vlaggen gaan die taken middenin de run draaien en muteren ze
dezelfde tabellen als de tests (StaleDataError, verdwenen testrijen).
De schedulers hebben hun eigen gerichte tests die ze expliciet aanroepen.
"""
import os

# ── Eigen testdatabase (taak #312) ───────────────────────────────────────────
# De suite draaide tegen dezelfde database als de draaiende app en wiste
# daarbij app-data (connector-bevestiging, concurrentprijzen). Vanaf nu
# draait de suite ALTIJD in een aparte database op dezelfde Postgres-server:
# standaard "<dbnaam>_test", overschrijfbaar via TEST_DATABASE_URL. De
# omgevingsvariabele DATABASE_URL wordt hier — vóór elke import van
# database.py — omgezet naar de testdatabase, met een harde guard die
# weigert te draaien als test- en app-database dezelfde zouden zijn.


def _effective_dbname(url: str) -> str:
    """Effectieve databasenaam zoals libpq die ziet — óók wanneer een
    `?dbname=`-queryparameter het URL-pad overschrijft. Weigert `service=`
    -indirectie (kan naar een willekeurige database wijzen)."""
    from psycopg2.extensions import parse_dsn
    params = parse_dsn(url)
    if params.get("service"):
        raise RuntimeError(
            "Testsuite geweigerd: database-URL gebruikt een libpq 'service'-"
            "verwijzing; de effectieve database is dan niet verifieerbaar.")
    name = (params.get("dbname") or "").strip()
    if not name:
        raise RuntimeError("Database-URL bevat geen databasenaam.")
    return name


def _derive_test_url(app_url: str) -> str:
    """Leid de testdatabase-URL af: zelfde server/credentials/query-opties
    (sslmode e.d.), databasenaam '<app-db>_test'. Een eventueel
    `dbname=`-queryparam wordt verwijderd zodat het pad de enige bron van de
    databasenaam is."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    parts = urlsplit(app_url)
    query = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() != "dbname"]
    app_db = _effective_dbname(app_url)
    return urlunsplit(parts._replace(path=f"/{app_db}_test",
                                     query=urlencode(query)))


def _assert_distinct_databases(app_url: str, test_url: str) -> None:
    """Harde guard: nooit tegen de app-database draaien. Vergelijkt de
    effectieve libpq-databasenamen, niet alleen het URL-pad."""
    if _effective_dbname(test_url) == _effective_dbname(app_url):
        raise RuntimeError(
            "Testsuite geweigerd: de testdatabase is gelijk aan de app-database "
            f"({_effective_dbname(app_url)!r}). Tests wissen app-data; zet "
            "TEST_DATABASE_URL naar een aparte database.")


def _setup_test_database() -> None:
    app_url = os.environ.get("DATABASE_URL")
    if not app_url:
        return  # database.py geeft zelf al een duidelijke fout

    test_url = (os.environ.get("TEST_DATABASE_URL") or "").strip() or _derive_test_url(app_url)
    _assert_distinct_databases(app_url, test_url)

    # Maak de testdatabase aan als hij nog niet bestaat (idempotent, en
    # bestand tegen gelijktijdige eerste runs: duplicate_database is dan ok).
    import psycopg2
    from psycopg2 import sql, errors as pg_errors

    conn = psycopg2.connect(app_url, connect_timeout=5)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                        (_effective_dbname(test_url),))
            if cur.fetchone() is None:
                try:
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(
                        sql.Identifier(_effective_dbname(test_url))))
                except pg_errors.DuplicateDatabase:
                    pass  # gelijktijdige suite-run was ons voor
    finally:
        conn.close()

    os.environ["DATABASE_URL"] = test_url
    os.environ["APP_DATABASE_URL_ORIGINAL"] = app_url  # alleen ter diagnose


_setup_test_database()

os.environ.setdefault("DISABLE_HEALTH_MONITOR", "true")
os.environ.setdefault("DISABLE_FEED_SYNC", "true")
os.environ.setdefault("DISABLE_DQ_SCAN", "true")
# Let op: de in-app scheduler in main.py leest DISABLE_DATA_QUALITY_SCAN
# (de losse scan-scheduler leest DISABLE_DQ_SCAN); zet beide, anders start
# de scan na de 90s-aanloop alsnog middenin een volledige suite-run.
os.environ.setdefault("DISABLE_DATA_QUALITY_SCAN", "true")
os.environ.setdefault("DISABLE_AI_BUDGET_CLEANUP", "true")
os.environ.setdefault("DISABLE_AI_KEY_MONITOR", "true")
os.environ.setdefault("DISABLE_SCRAPE_SCHEDULER", "true")
# Voorkom dat seed_hierarchy_from_excel() tijdens TestClient(app)-startups
# de hiërarchietabellen muteert. Hiërarchieboom-tests (bijv. test_hierarchy_
# autobuild.py) deactiveren tijdelijk handmatige nodes; een startup-import
# in die toestand zou de boomtoestand vernielen die de test vereist.
os.environ.setdefault("DISABLE_HIERARCHY_SEED", "true")


# ── Cross-run serialisatie van hiërarchie-mutatie-modules ────────────────────
# Validatie- en code-review-runs draaien de volledige suite soms gelijktijdig
# tegen dezelfde gedeelde dev-DB. Modules die de producthiërarchie globaal
# muteren (autobuild/retire, import-apply, deactivate_missing) of er direct
# van afhangen, serialiseren we met een sessie-gebonden Postgres advisory
# lock zodat parallelle runs elkaars boomtoestand niet vernielen.
import pytest as _pytest

HIERARCHY_SUITE_LOCK_KEY = 774411277


@_pytest.fixture(scope="session", autouse=True)
def _bootstrap_test_database_schema():
    """Zorg dat de (verse) testdatabase schema + seeds heeft vóór welke test
    dan ook — ook tests die de database direct benaderen zonder eerst een
    TestClient te starten. Eén TestClient-startup draait de volledige
    idempotente bootstrap uit main.py (create_all, migraties, canonical,
    users/authz-seed) en zet _db_bootstrap_done zodat latere TestClients
    hem overslaan."""
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app):
        pass
    yield


# ── Gedeelde opruiming van hiërarchie-test-importjobs ───────────────────────
# Incident 25-08: achtergebleven test-importjobs met status "geimporteerd"
# maskeerden de echte Excel-import als "laatst toegepaste import", waardoor
# auto_assign_new_products geen echte producten meer koppelde en
# categoriefilters lege ranking-data toonden. Elke test die een
# hiërarchie-import applyt MOET deze helper in zijn fixture-teardown
# aanroepen (teardowns draaien óók bij assert-failures) met een unieke,
# testrun-specifieke bestandsnaam-prefix.

_HIERARCHY_TEST_JOB_PREFIXES: set[str] = set()
_HIERARCHY_TEST_JOB_IDS: set[int] = set()


def register_hierarchy_test_job_ids(job_ids) -> None:
    """Registreer exact bekende test-job-ids voor de suite-brede residu-check.
    Voor tests (zoals de Excel-seedtests) waarvan de jobs de échte
    Excel-bestandsnaam dragen en dus niet via een prefix te herkennen zijn.
    Registreer direct ná het aanmaken/applyen, vóór enige assert."""
    _HIERARCHY_TEST_JOB_IDS.update(int(j) for j in job_ids)


def purge_hierarchy_import_jobs_by_ids(db, job_ids) -> None:
    """Als purge_hierarchy_import_jobs, maar op exact bekende job-ids:
    assignments.import_job_id nullen, changelog/staging wissen, jobs
    verwijderen. Committen doet de aanroeper."""
    import models
    job_ids = [int(j) for j in job_ids]
    if not job_ids:
        return
    register_hierarchy_test_job_ids(job_ids)
    A = models.ProductHierarchyAssignment
    S = models.ProductHierarchyStagingRow
    C = models.ProductHierarchyChangeLog
    db.query(A).filter(A.import_job_id.in_(job_ids)).update(
        {A.import_job_id: None}, synchronize_session=False)
    db.query(C).filter(C.import_job_id.in_(job_ids)).delete(
        synchronize_session=False)
    db.query(S).filter(S.job_id.in_(job_ids)).delete(
        synchronize_session=False)
    db.query(models.ImportJob).filter(
        models.ImportJob.id.in_(job_ids)).delete(synchronize_session=False)


def register_hierarchy_test_prefix(filename_prefix: str) -> None:
    """Registreer een test-bestandsnaam-prefix voor de suite-brede
    residu-check. purge_hierarchy_import_jobs registreert al zelf; roep dit
    apart aan als je jobs aanmaakt vóórdat de teardown ooit kan draaien."""
    assert filename_prefix, "lege prefix zou echte imports matchen"
    _HIERARCHY_TEST_JOB_PREFIXES.add(filename_prefix)


def purge_hierarchy_import_jobs(db, filename_prefix: str) -> list[int]:
    """
    Verwijder alle product_hierarchy-ImportJobs waarvan de bestandsnaam met
    `filename_prefix` begint, inclusief alle verwijzingen:
      - assignments.import_job_id op NULL (retire/supersede stempelt job-ids
        ook op rijen die niet met de testprefix zelf te vinden zijn),
      - changelog- en staging-rijen van die jobs wissen,
      - de jobs zelf verwijderen.
    Committen doet de aanroeper (samen met de rest van zijn teardown).
    Retourneert de verwijderde job-ids.
    """
    import models
    register_hierarchy_test_prefix(filename_prefix)
    J = models.ImportJob
    A = models.ProductHierarchyAssignment
    S = models.ProductHierarchyStagingRow
    C = models.ProductHierarchyChangeLog
    job_ids = [j for (j,) in db.query(J.id).filter(
        J.upload_type == "product_hierarchy",
        J.filename.like(f"{filename_prefix}%"))]
    if job_ids:
        db.query(A).filter(A.import_job_id.in_(job_ids)).update(
            {A.import_job_id: None}, synchronize_session=False)
        db.query(C).filter(C.import_job_id.in_(job_ids)).delete(
            synchronize_session=False)
        db.query(S).filter(S.job_id.in_(job_ids)).delete(
            synchronize_session=False)
        db.query(J).filter(J.id.in_(job_ids)).delete(synchronize_session=False)
    return job_ids


@_pytest.fixture(scope="session", autouse=True)
def _hierarchy_import_residue_check():
    """Suite-brede sanity-check: faal na afloop als er hiërarchie-importjobs
    met status "geimporteerd" achterblijven die van een geregistreerde
    testprefix zijn (en dus niet van de echte Excel-import)."""
    yield
    if not (_HIERARCHY_TEST_JOB_PREFIXES or _HIERARCHY_TEST_JOB_IDS):
        return
    from database import SessionLocal
    import models
    db = SessionLocal()
    try:
        J = models.ImportJob
        leftovers = []
        for pfx in sorted(_HIERARCHY_TEST_JOB_PREFIXES):
            leftovers.extend(db.query(J.id, J.filename, J.status).filter(
                J.upload_type == "product_hierarchy",
                J.status == "geimporteerd",
                J.filename.like(f"{pfx}%")).all())
        if _HIERARCHY_TEST_JOB_IDS:
            leftovers.extend(db.query(J.id, J.filename, J.status).filter(
                J.upload_type == "product_hierarchy",
                J.status == "geimporteerd",
                J.id.in_(sorted(_HIERARCHY_TEST_JOB_IDS))).all())
        if leftovers:
            raise AssertionError(
                "Achtergebleven hiërarchie-test-importjobs met status "
                f"'geimporteerd': {leftovers}. Deze maskeren de echte "
                "Excel-import voor auto_assign_new_products — ruim ze op "
                "via purge_hierarchy_import_jobs in de fixture-teardown.")
    finally:
        db.close()


@_pytest.fixture(scope="module")
def hierarchy_suite_lock():
    from sqlalchemy import text as _text
    from database import engine as _engine
    conn = _engine.connect()
    if conn.dialect.name != "postgresql":
        yield
        conn.close()
        return
    conn.execute(_text("SELECT pg_advisory_lock(:k)"),
                 {"k": HIERARCHY_SUITE_LOCK_KEY})
    try:
        yield
    finally:
        try:
            conn.execute(_text("SELECT pg_advisory_unlock(:k)"),
                         {"k": HIERARCHY_SUITE_LOCK_KEY})
        finally:
            conn.close()
