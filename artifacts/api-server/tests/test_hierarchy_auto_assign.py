"""Tests voor automatische toewijzing van nieuwe feed-producten aan de
Excel-categorieboom (taak #282): na een feed-sync krijgen nieuw binnengekomen
producten automatisch een toewijzing o.b.v. de staging-rijen van de laatst
toegepaste hiërarchie-import. Bestaande toewijzingen worden nooit overschreven.
"""
import uuid
from datetime import datetime, timedelta

import pytest

import models
from database import SessionLocal
from services.product_hierarchy import (
    AUTO_ASSIGN_SOURCE, apply_job, auto_assign_new_products, stage_rows,
    validate_job,
)

PFX = f"AAT{uuid.uuid4().hex[:6].upper()}"


def _mk_job(db) -> models.ImportJob:
    job = models.ImportJob(upload_type="product_hierarchy",
                           filename=f"{PFX}.csv", status="wachtend",
                           uploaded_by="tester")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@pytest.fixture()
def scenario(hierarchy_suite_lock):
    """
    Toegepaste import met 3 staging-rijen:
      - rij voor een al bestaand product (drs_id-match bij apply),
      - rij met een feed-productcode die op dat moment nergens op matcht,
      - rij met een EAN die op dat moment nergens op matcht.
    Daarna komen er 'via de feed' nieuwe producten bij.
    """
    db = SessionLocal()

    # apply_job retireert een eventueel bestaande auto-boom (nodes inactief,
    # auto-toewijzingen superseded) in de gedeelde dev-DB. Snapshot die staat
    # zodat de teardown hem kan herstellen en andere suites (autobuild) geen
    # gepollueerde uitgangssituatie zien.
    from services.hierarchy_autobuild import AUTO_SOURCE
    N = models.ProductHierarchyNode
    A0 = models.ProductHierarchyAssignment
    auto_node_ids = [nid for (nid,) in db.query(N.id).filter(
        N.source == AUTO_SOURCE, N.is_active.is_(True))]
    auto_assign_ids = [aid for (aid,) in db.query(A0.id).filter(
        A0.source == AUTO_SOURCE, A0.status == "active")]

    sku_exist = f"{PFX}-EXIST"
    db.add(models.DimProduct(sku_id=sku_exist, product_name=f"{PFX} bestaand"))
    db.commit()

    job = _mk_job(db)
    mapping = {"option_col": "optionid", "product_col": "productcode",
               "path_col": "path", "separator": " > "}
    rows = [
        {"optionId": f"{PFX}-O1", "productCode": sku_exist,
         "path": f"{PFX}-Kantoor > {PFX}-Papier"},
        {"optionId": f"{PFX}-O2", "productCode": f"{PFX}-FEED-42",
         "path": f"{PFX}-Kantoor > {PFX}-Pennen"},
        {"optionId": "", "productCode": f"{PFX}-EAN-13",
         "path": f"{PFX}-Kantoor > {PFX}-Markers"},
    ]
    stage_rows(db, job, rows, dict(mapping))
    validate_job(db, job)
    db.commit()
    apply_job(db, job, username="tester")
    # Garandeer dat déze import de "laatst toegepaste" is, ook als de
    # gedeelde dev-DB al echte imports bevat (shared-DB test isolation).
    db.refresh(job)
    job.completed_at = datetime.utcnow() + timedelta(days=365)
    db.commit()

    yield db, job, sku_exist

    N = models.ProductHierarchyNode
    A = models.ProductHierarchyAssignment
    P = models.ProductHierarchyPath
    S = models.ProductHierarchyStagingRow
    C = models.ProductHierarchyChangeLog
    db.rollback()
    skus = [s for (s,) in db.query(models.DimProduct.sku_id)
            .filter(models.DimProduct.sku_id.like(f"{PFX}%"))]
    node_ids = [nid for (nid,) in db.query(N.id)
                .filter(N.path_names.like(f"%{PFX}%"))]
    if node_ids:
        db.query(A).filter(A.node_id.in_(node_ids)).delete(synchronize_session=False)
        db.query(P).filter(P.leaf_node_id.in_(node_ids)).delete(synchronize_session=False)
        db.query(C).filter(C.node_id.in_(node_ids)).delete(synchronize_session=False)
    if skus:
        db.query(A).filter(A.sku_id.in_(skus)).delete(synchronize_session=False)
        db.query(C).filter(C.sku_id.in_(skus)).delete(synchronize_session=False)
    if node_ids:
        for n in sorted(db.query(N).filter(N.id.in_(node_ids)),
                        key=lambda x: -(x.level or 0)):
            db.delete(n)
    # ALLE importjobs van deze testrun opruimen (job én eventuele job2's),
    # óók als een test halverwege faalde: een achtergebleven job met status
    # "geimporteerd" en toekomstige completed_at zou anders de "laatst
    # toegepaste import" worden en auto_assign in productiepaden breken.
    J = models.ImportJob
    job_ids = [j for (j,) in db.query(J.id).filter(
        J.upload_type == "product_hierarchy",
        J.filename == f"{PFX}.csv")]
    if job_ids:
        db.query(A).filter(A.import_job_id.in_(job_ids)).update(
            {A.import_job_id: None}, synchronize_session=False)
        db.query(S).filter(S.job_id.in_(job_ids)).delete(synchronize_session=False)
        db.query(C).filter(C.import_job_id.in_(job_ids)).delete(synchronize_session=False)
        db.query(J).filter(J.id.in_(job_ids)).delete(synchronize_session=False)
    # Herstel de auto-boomstaat die apply_job heeft geretireerd.
    if auto_node_ids:
        db.query(N).filter(N.id.in_(auto_node_ids)).update(
            {"is_active": True}, synchronize_session=False)
    if auto_assign_ids:
        db.query(A0).filter(A0.id.in_(auto_assign_ids)).update(
            {"status": "active", "valid_to": None},
            synchronize_session=False)
    db.commit()
    if skus:
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_(skus)).delete(synchronize_session=False)
        db.commit()
    db.close()


def _active(db, sku):
    A = models.ProductHierarchyAssignment
    return (db.query(A).filter(A.sku_id == sku, A.status == "active").all())


def _leaf(db, name_suffix):
    N = models.ProductHierarchyNode
    return (db.query(N).filter(N.name == f"{PFX}-{name_suffix}").one())


def test_nieuwe_feed_producten_worden_automatisch_toegewezen(scenario):
    db, job, _ = scenario
    # "Feed-sync" levert nieuwe producten: één matcht op feed-id, één op EAN,
    # één komt niet in de Excel voor.
    sku_feed = f"{PFX}-NEW-FEED"
    sku_ean = f"{PFX}-NEW-EAN"
    sku_none = f"{PFX}-NEW-NONE"
    db.add(models.DimProduct(sku_id=sku_feed, product_name="nieuw feed",
                             raw_attributes={"id": f"{PFX}-FEED-42"}))
    db.add(models.DimProduct(sku_id=sku_ean, product_name="nieuw ean",
                             ean=f"{PFX}-EAN-13"))
    db.add(models.DimProduct(sku_id=sku_none, product_name="nieuw los"))
    db.commit()

    res = auto_assign_new_products(db)
    assert res.get("job_id") == job.id
    assert res["toegewezen"] >= 2

    a_feed = _active(db, sku_feed)
    assert len(a_feed) == 1
    assert a_feed[0].node_id == _leaf(db, "Pennen").id
    assert a_feed[0].source == AUTO_ASSIGN_SOURCE
    assert a_feed[0].import_job_id == job.id

    a_ean = _active(db, sku_ean)
    assert len(a_ean) == 1
    assert a_ean[0].node_id == _leaf(db, "Markers").id

    assert _active(db, sku_none) == []

    # changelog-rij aanwezig met herkomst
    C = models.ProductHierarchyChangeLog
    logrow = (db.query(C).filter(C.sku_id == sku_feed,
                                 C.change_type == "assignment_created",
                                 C.source == AUTO_ASSIGN_SOURCE).first())
    assert logrow is not None

    # Idempotent: tweede aanroep wijst niets extra toe aan deze producten.
    auto_assign_new_products(db)
    assert len(_active(db, sku_feed)) == 1
    assert len(_active(db, sku_ean)) == 1


def test_bestaande_toewijzing_wordt_nooit_overschreven(scenario):
    db, job, _ = scenario
    # Nieuw product dat op de Excel zou matchen (feed-id), maar al handmatig
    # aan een ándere node is toegewezen — moet onaangeroerd blijven.
    sku_manual = f"{PFX}-NEW-MANUAL"
    db.add(models.DimProduct(sku_id=sku_manual, product_name="handmatig",
                             raw_attributes={"id": f"{PFX}-FEED-42"}))
    db.commit()
    manual_node = _leaf(db, "Markers")   # bewust een andere node dan Pennen
    db.add(models.ProductHierarchyAssignment(
        sku_id=sku_manual, node_id=manual_node.id, status="active",
        source="manual", assigned_by="gebruiker"))
    db.commit()

    auto_assign_new_products(db)

    rows = _active(db, sku_manual)
    assert len(rows) == 1
    assert rows[0].node_id == manual_node.id
    assert rows[0].source == "manual"


def test_zonder_toegepaste_import_gebeurt_niets(scenario, monkeypatch):
    db, job, _ = scenario
    # Deterministisch, onafhankelijk van gedeelde DB-staat: forceer het
    # "geen toegepaste import"-pad.
    import services.product_hierarchy as ph
    monkeypatch.setattr(ph, "last_applied_import", lambda _db: None)
    res = auto_assign_new_products(db)
    assert res.get("skipped") is True


def test_nieuwste_toegepaste_import_wint_van_verouderde(scenario):
    db, job, sku_exist = scenario
    # Regressie voor de lock-volgorde: de job wordt pas ná het advisory lock
    # bepaald, dus een intussen toegepaste NIEUWERE import moet leidend zijn.
    # Tweede import verplaatst FEED-42 naar een ander pad; een daarna
    # binnengekomen feed-product moet het pad van de nieuwste import krijgen.
    job2 = _mk_job(db)
    mapping = {"option_col": "optionid", "product_col": "productcode",
               "path_col": "path", "separator": " > "}
    stage_rows(db, job2, [
        {"optionId": f"{PFX}-O9", "productCode": f"{PFX}-FEED-42",
         "path": f"{PFX}-Kantoor > {PFX}-Markers"},
    ], dict(mapping))
    validate_job(db, job2)
    db.commit()
    apply_job(db, job2, username="tester")
    db.refresh(job2)
    job2.completed_at = datetime.utcnow() + timedelta(days=366)
    db.commit()

    sku_new = f"{PFX}-NEW-LATE"
    db.add(models.DimProduct(sku_id=sku_new, product_name="laatkomer",
                             raw_attributes={"id": f"{PFX}-FEED-42"}))
    db.commit()

    res = auto_assign_new_products(db)
    assert res.get("job_id") == job2.id
    rows = _active(db, sku_new)
    assert len(rows) == 1
    assert rows[0].node_id == _leaf(db, "Markers").id
    assert rows[0].import_job_id == job2.id
    # job2 wordt door de scenario-finalizer opgeruimd (PFX-bestandsnaam).


def test_lopende_apply_blokkeert_auto_assign(scenario):
    db, job, _ = scenario
    # Interleaving-regressie: apply_job claimt de job met een commit naar
    # 'bezig' vóórdat hij het advisory lock neemt. Een auto-assign die in dat
    # venster start mag NIET op de vorige import doorwerken; hij moet skippen
    # zolang er een apply onderweg is, en na afloop de nieuwe import gebruiken.
    job2 = _mk_job(db)
    mapping = {"option_col": "optionid", "product_col": "productcode",
               "path_col": "path", "separator": " > "}
    stage_rows(db, job2, [
        {"optionId": f"{PFX}-O9", "productCode": f"{PFX}-FEED-42",
         "path": f"{PFX}-Kantoor > {PFX}-Markers"},
    ], dict(mapping))
    validate_job(db, job2)
    db.commit()

    # Simuleer het racevenster in een TWEEDE sessie: claim gecommit ('bezig'),
    # lock nog niet genomen.
    db2 = SessionLocal()
    try:
        claimed = (db2.query(models.ImportJob)
                   .filter(models.ImportJob.id == job2.id,
                           models.ImportJob.status == "gevalideerd")
                   .update({"status": "bezig"}, synchronize_session=False))
        db2.commit()
        assert claimed == 1

        sku_new = f"{PFX}-NEW-RACE"
        db.add(models.DimProduct(sku_id=sku_new, product_name="race",
                                 raw_attributes={"id": f"{PFX}-FEED-42"}))
        db.commit()

        res = auto_assign_new_products(db)
        assert res.get("skipped") is True          # apply onderweg → overslaan
        assert _active(db, sku_new) == []          # géén verouderde koppeling

        # Apply afronden (status terug zodat apply_job zelf kan claimen) …
        db2.query(models.ImportJob).filter(models.ImportJob.id == job2.id) \
            .update({"status": "gevalideerd"}, synchronize_session=False)
        db2.commit()
    finally:
        db2.close()
    apply_job(db, job2, username="tester")
    db.refresh(job2)
    job2.completed_at = datetime.utcnow() + timedelta(days=366)
    db.commit()

    # … daarna gebruikt de auto-assign de nieuwste import.
    res = auto_assign_new_products(db)
    assert res.get("job_id") == job2.id
    rows = _active(db, f"{PFX}-NEW-RACE")
    assert len(rows) == 1
    assert rows[0].node_id == _leaf(db, "Markers").id
    # job2 wordt door de scenario-finalizer opgeruimd (PFX-bestandsnaam).


def test_sku_van_gekoppeld_product_wint_van_ean_collision(scenario):
    db, job, _ = scenario
    # Staging-code {PFX}-COLL (pad Pennen). Product A heeft die code als
    # SKU en is al gekoppeld; product B (ongekoppeld) heeft hem als EAN.
    # validate_job zou de rij naar A resolven (SKU heeft voorrang) —
    # B mag dus GEEN toewijzing krijgen.
    code = f"{PFX}-COLL"
    sku_b = f"{PFX}-NEW-COLL-B"
    node_a = _leaf(db, "Papier")
    db.add(models.DimProduct(sku_id=code, product_name="collision A"))
    db.add(models.DimProduct(sku_id=sku_b, product_name="collision B",
                             ean=code))
    db.commit()
    db.add(models.ProductHierarchyAssignment(
        sku_id=code, node_id=node_a.id, status="active",
        source="manual", assigned_by="gebruiker"))
    # extra staging-rij met deze code
    db.add(models.ProductHierarchyStagingRow(
        job_id=job.id, row_number=99, product_code=code,
        path_names=[f"{PFX}-Kantoor", f"{PFX}-Pennen"], status="geldig"))
    db.commit()

    auto_assign_new_products(db)

    # B blijft ongekoppeld (de rij resolvet naar A, dat al gekoppeld is) …
    assert _active(db, sku_b) == []
    # … en A blijft onaangeroerd op zijn bestaande node.
    rows_a = _active(db, code)
    assert len(rows_a) == 1 and rows_a[0].node_id == node_a.id


def test_eerste_rij_wint_bij_meerdere_matchende_codes(scenario):
    db, job, _ = scenario
    # Eén nieuw product matcht op TWEE staging-rijen met verschillende paden:
    # feed-id → rij "Pennen" (rij 2) en EAN → rij "Markers" (rij 3).
    # Net als bij validate_job wint de eerste rij die resolvet: Pennen.
    sku = f"{PFX}-NEW-BOTH"
    db.add(models.DimProduct(sku_id=sku, product_name="beide matches",
                             raw_attributes={"id": f"{PFX}-FEED-42"},
                             ean=f"{PFX}-EAN-13"))
    db.commit()

    auto_assign_new_products(db)

    rows = _active(db, sku)
    assert len(rows) == 1
    assert rows[0].node_id == _leaf(db, "Pennen").id
