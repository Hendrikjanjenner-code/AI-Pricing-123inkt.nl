"""
Tests voor concurrent-matching en datakwaliteit zonder EAN in de feed.

De standaard PriceShape-exportfeed bevat geen GTIN/EAN-kolom; producten worden
geïmporteerd op itemGroupId en ean blijft None. Deze tests verifiëren dat:

1. _normalize_wide_csv: ean is None voor producten zonder gtin-kolom.
2. build_ai_matches: ean_match=False en juiste explanation_nl als product geen EAN heeft.
3. build_ai_matches: ean_match=True en juiste explanation_nl als product wél EAN heeft.
4. MISSING_EAN data-quality: feedbreed signaal (info) wanneer ≥95 % van de SKU's geen EAN heeft.
5. MISSING_EAN data-quality: warning wanneer slechts een deel van de SKU's geen EAN heeft.
"""
import os
import sys
import uuid
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import feed_ingest as fi
from routes.data_quality import _detect_issues


# ── Eenvoudige unit-tests zonder DB ──────────────────────────────────────────

WIDE_NO_EAN = [
    {
        "itemgroupid": "SKU-001",
        "name": "Testproduct A",
        "priceinclvat": "10,00",
        "costpriceexclvat": "5,00",
        "ppc_producttype": "office > pens",
        "vendor_1 domain": "comp-a.nl",
        "vendor_1 price": "9,50",
        "vendor_1 stockstatus": "InStock",
        "vendor_1 producturl": "https://comp-a.nl/p/1",
        "vendor_2 domain": "comp-b.nl",
        "vendor_2 price": "9,80",
        "vendor_2 stockstatus": "OutOfStock",
    },
    {
        "itemgroupid": "SKU-002",
        "name": "Testproduct B",
        "priceinclvat": "20,00",
        "costpriceexclvat": "12,00",
        "ppc_producttype": "office > paper",
        "vendor_1 domain": "comp-a.nl",
        "vendor_1 price": "18,99",
    },
]


def test_wide_no_ean_produces_none_ean():
    """Zonder gtin-kolom is ean None — geen verzonnen EAN-code."""
    catalog, comp = fi._normalize_flat(WIDE_NO_EAN)
    assert len(catalog) == 2
    for p in catalog:
        assert p["ean"] is None, f"Verwacht ean=None voor {p['sku_id']}, maar was {p['ean']!r}"


def test_wide_no_ean_sku_id_is_item_group_id():
    """sku_id is de itemGroupId wanneer er geen GTIN beschikbaar is."""
    catalog, _ = fi._normalize_flat(WIDE_NO_EAN)
    sku_ids = {p["sku_id"] for p in catalog}
    assert "SKU-001" in sku_ids
    assert "SKU-002" in sku_ids


def test_wide_no_ean_competitor_rows_present():
    """Concurrentprijzen worden correct geëxtraheerd ook zonder EAN."""
    catalog, comp = fi._normalize_flat(WIDE_NO_EAN)
    assert len(comp) == 3  # SKU-001 heeft 2 vendors, SKU-002 heeft 1
    domains = {r["competitor_name"] for r in comp}
    assert "comp-a.nl" in domains
    assert "comp-b.nl" in domains


# ── DB-gebaseerde tests voor build_ai_matches ─────────────────────────────────

@pytest.fixture(scope="module")
def db():
    from database import SessionLocal
    session = SessionLocal()
    yield session
    session.close()


def _make_product(db, sku_id, ean=None, current_price=10.0):
    import models
    # Verwijder eerst eventuele resten van een vorige run.
    db.query(models.AiMatchResult).filter(
        models.AiMatchResult.own_sku_id == sku_id).delete(synchronize_session=False)
    db.query(models.FactCompetitorPriceDaily).filter(
        models.FactCompetitorPriceDaily.sku_id == sku_id).delete(synchronize_session=False)
    db.query(models.DimProduct).filter(
        models.DimProduct.sku_id == sku_id).delete(synchronize_session=False)
    db.commit()

    p = models.DimProduct(
        sku_id=sku_id, product_name=f"Test {sku_id}",
        brand="Brand", category="Cat", strategy_type="protect",
        current_price=current_price, ean=ean, is_active=True,
    )
    db.add(p)
    db.commit()
    return p


def _make_comp_price(db, sku_id, competitor_name, price):
    import models
    row = models.FactCompetitorPriceDaily(
        date=date.today(), sku_id=sku_id,
        competitor_name=competitor_name, price=price,
        url=f"https://{competitor_name}/p/{sku_id}", source="priceshape",
    )
    db.add(row)
    db.commit()
    return row


def _teardown(db, *sku_ids):
    import models
    ids = list(sku_ids)
    for model_cls, col in [
        (models.AiMatchResult, models.AiMatchResult.own_sku_id),
        (models.FactCompetitorPriceDaily, models.FactCompetitorPriceDaily.sku_id),
    ]:
        db.query(model_cls).filter(col.in_(ids)).delete(synchronize_session=False)
    db.query(models.DimProduct).filter(
        models.DimProduct.sku_id.in_(ids)).delete(synchronize_session=False)
    db.commit()


class TestBuildAiMatchesNoEan:
    """build_ai_matches met producten die geen EAN hebben (standaard PriceShape-feed)."""

    SKU = f"EANLESS-{uuid.uuid4().hex[:8]}"
    COMP = "test-no-ean.nl"

    def test_ean_match_false_when_no_ean(self, db):
        try:
            _make_product(db, self.SKU, ean=None, current_price=15.0)
            _make_comp_price(db, self.SKU, self.COMP, 14.0)

            count = fi.build_ai_matches(db)
            assert count >= 1

            import models
            match = db.query(models.AiMatchResult).filter(
                models.AiMatchResult.own_sku_id == self.SKU,
                models.AiMatchResult.competitor_name == self.COMP,
                models.AiMatchResult.run_date == date.today(),
            ).first()
            assert match is not None, "Verwacht één AiMatchResult voor het EAN-loze SKU"
            assert match.ean_match is False, \
                f"ean_match moet False zijn als product geen EAN heeft, maar was {match.ean_match!r}"
            assert match.match_type == "Exact"
            assert match.confidence == 1.0
        finally:
            _teardown(db, self.SKU)

    def test_explanation_mentions_item_group_id_when_no_ean(self, db):
        try:
            _make_product(db, self.SKU, ean=None, current_price=15.0)
            _make_comp_price(db, self.SKU, self.COMP, 14.0)
            fi.build_ai_matches(db)

            import models
            match = db.query(models.AiMatchResult).filter(
                models.AiMatchResult.own_sku_id == self.SKU,
                models.AiMatchResult.competitor_name == self.COMP,
                models.AiMatchResult.run_date == date.today(),
            ).first()
            assert match is not None
            # De uitleg moet verwijzen naar itemGroupId, niet naar EAN/GTIN
            exp = match.explanation_nl or ""
            assert "itemGroupId" in exp or "itemgroupid" in exp.lower(), \
                f"Verwacht verwijzing naar itemGroupId in uitleg, maar was: {exp!r}"
            assert "GTIN" not in exp or "geen GTIN" in exp, \
                f"Uitleg mag niet claimen dat GTIN gebruikt is: {exp!r}"
        finally:
            _teardown(db, self.SKU)


class TestBuildAiMatchesWithEan:
    """build_ai_matches met producten die wél een EAN hebben."""

    SKU = f"EANFULL-{uuid.uuid4().hex[:8]}"
    EAN = f"87{uuid.uuid4().int % 10**11:011d}"
    COMP = "test-with-ean.nl"

    def test_ean_match_true_when_ean_present(self, db):
        try:
            _make_product(db, self.SKU, ean=self.EAN, current_price=20.0)
            _make_comp_price(db, self.SKU, self.COMP, 18.0)
            fi.build_ai_matches(db)

            import models
            match = db.query(models.AiMatchResult).filter(
                models.AiMatchResult.own_sku_id == self.SKU,
                models.AiMatchResult.competitor_name == self.COMP,
                models.AiMatchResult.run_date == date.today(),
            ).first()
            assert match is not None
            assert match.ean_match is True, \
                f"ean_match moet True zijn als product een EAN heeft, maar was {match.ean_match!r}"
            exp = match.explanation_nl or ""
            assert self.EAN in exp, \
                f"Verwacht EAN {self.EAN!r} in uitleg, maar was: {exp!r}"
        finally:
            _teardown(db, self.SKU)


# ── Data-quality: feedbreed vs. partieel MISSING_EAN ──────────────────────────

class TestMissingEanFeedWide:
    """MISSING_EAN rapporteert 'info' als de GEHELE feed geen EAN heeft."""

    SKUS = [f"EANWIDE-{uuid.uuid4().hex[:8]}-{i}" for i in range(5)]

    def test_feed_wide_missing_ean_is_info(self, db):
        import models
        try:
            for sku in self.SKUS:
                db.query(models.DimProduct).filter(
                    models.DimProduct.sku_id == sku).delete(synchronize_session=False)
            db.commit()
            for sku in self.SKUS:
                db.add(models.DimProduct(
                    sku_id=sku, product_name=f"Wide {sku}",
                    brand="B", category="C", strategy_type="protect",
                    current_price=10.0, ean=None, is_active=True,
                ))
            db.commit()

            total = db.query(models.DimProduct).count()
            detected = _detect_issues(db, total)
            ean_issue = next((d for d in detected if d["issue_code"] == "MISSING_EAN"), None)
            assert ean_issue is not None, "MISSING_EAN issue moet aanwezig zijn"
            # Als nagenoeg alle SKU's geen EAN hebben → feedbreed signaal op info-niveau
            missing = db.query(models.DimProduct).filter(
                (models.DimProduct.ean.is_(None)) | (models.DimProduct.ean == "")).count()
            if missing >= int(total * 0.95):
                assert ean_issue["severity"] == "info", (
                    f"Feedbreed EAN-gemis moet severity='info' zijn, maar was {ean_issue['severity']!r}"
                )
                assert "itemGroupId" in (ean_issue.get("message") or "") or \
                       "itemGroupId" in (ean_issue.get("title") or ""), \
                    "Feedbreed signaal moet verwijzen naar itemGroupId-koppeling"
        finally:
            _teardown(db, *self.SKUS)

    def test_feed_wide_missing_ean_affected_count_is_total(self, db):
        """affected_count bevat het werkelijke aantal SKU's zonder EAN."""
        import models
        try:
            for sku in self.SKUS:
                db.query(models.DimProduct).filter(
                    models.DimProduct.sku_id == sku).delete(synchronize_session=False)
            db.commit()
            for sku in self.SKUS:
                db.add(models.DimProduct(
                    sku_id=sku, product_name=f"Wide {sku}",
                    brand="B", category="C", strategy_type="protect",
                    current_price=10.0, ean=None, is_active=True,
                ))
            db.commit()
            total = db.query(models.DimProduct).count()
            detected = _detect_issues(db, total)
            ean_issue = next((d for d in detected if d["issue_code"] == "MISSING_EAN"), None)
            assert ean_issue is not None
            assert ean_issue["affected_count"] >= len(self.SKUS)
        finally:
            _teardown(db, *self.SKUS)


class TestMissingEanPartial:
    """MISSING_EAN rapporteert 'warning' als slechts een deel van de SKU's geen EAN heeft.

    De echte DB kan een volledige catalogus zonder EAN bevatten (feedbreed scenario).
    De partiële logica wordt getest door een gesimuleerd total_skus door te geven:
    als missing_ean < 5% van total_skus, moet de drempel niet worden gehaald → warning.
    """

    def test_partial_missing_ean_is_warning(self, db):
        """Beslissingslogica: als missing_ean < 95% van total_skus → severity='warning'."""
        import models
        # Haal het werkelijke aantal SKU's zonder EAN op uit de DB.
        missing = db.query(models.DimProduct).filter(
            (models.DimProduct.ean.is_(None)) | (models.DimProduct.ean == "")).count()
        if missing == 0:
            pytest.skip("Geen SKU's zonder EAN in de DB; partieel scenario niet testbaar.")

        # Geef een total_skus door die de missing_ean ruim onder de 95%-drempel brengt.
        # Bij missing_ean * 20 is het aandeel zonder EAN slechts ~5% van het gesimuleerde totaal.
        simulated_total = missing * 20
        detected = _detect_issues(db, simulated_total)
        ean_issue = next((d for d in detected if d["issue_code"] == "MISSING_EAN"), None)
        assert ean_issue is not None, "MISSING_EAN issue moet aanwezig zijn als er SKU's zonder EAN zijn"
        assert ean_issue["severity"] == "warning", (
            f"Als EAN-gemis < 5% van catalogus is, moet severity='warning' zijn "
            f"(missing={missing}, total={simulated_total}), maar was {ean_issue['severity']!r}"
        )
