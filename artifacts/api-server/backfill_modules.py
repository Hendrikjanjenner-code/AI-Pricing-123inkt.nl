"""
Backfill demo data voor de 4 nieuwe modules:
- dim_competitor (3 concurrenten)
- competitor_scrape_config (selectors per concurrent)
- fact_scrape_result (demo scrape-uitkomsten)
- fact_competitor_offer_daily (dagelijkse aanbiedingen per SKU)
- product_match (gekoppelde producten)
- fact_monitoring_alert (monitoring-alerts)
- price_execution_job + price_execution_line (uitvoering-batch)

Businessscenario (uit spec):
- Toner eigen prijs €250
- Concurrent A (Printshop.nl) prijs €235, goede voorraad, hoge CSRS
- Concurrent B (GoedkoopToner.nl) prijs €199, lage CSRS, lage CSS
- Concurrent C (OfficeMax.nl) prijs €210, out-of-stock
- Concurrent B wordt NIET gevolgd ondanks laagste prijs
- Concurrent A is primaire referent
- Referentieprijs = gewogen mediaan, niet minimumprijs
"""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
from models import (
    DimCompetitor, CompetitorScrapeConfig, FactScrapeResult,
    FactCompetitorOfferDaily, ProductMatch, FactMonitoringAlert,
    PriceExecutionJob, PriceExecutionLine,
    DimProduct, FactPricingRecommendationDaily,
)

db = SessionLocal()

vandaag = date.today()
gisteren = vandaag - timedelta(days=1)


def skip(model, **filter_kwargs):
    """Geeft True terug als er al records bestaan met deze filters."""
    return db.query(model).filter_by(**filter_kwargs).first() is not None


# ─── dim_competitor ────────────────────────────────────────────────────────
if db.query(DimCompetitor).count() > 0:
    print("DimCompetitor already exists — skipping.")
else:
    concurrenten = [
        DimCompetitor(
            competitor_name="Printshop.nl",
            base_url="https://www.printshop.nl",
            competitor_type="online",
            default_relevance_score=0.85,
            channel_relevance={"B2B": 0.9, "B2C": 0.7},
            scraping_enabled=True,
            active=True,
        ),
        DimCompetitor(
            competitor_name="GoedkoopToner.nl",
            base_url="https://www.goedkooptoner.nl",
            competitor_type="online",
            default_relevance_score=0.40,
            channel_relevance={"B2B": 0.3, "B2C": 0.6},
            scraping_enabled=True,
            active=True,
        ),
        DimCompetitor(
            competitor_name="OfficeMax.nl",
            base_url="https://www.officemax.nl",
            competitor_type="online",
            default_relevance_score=0.65,
            channel_relevance={"B2B": 0.7, "B2C": 0.8},
            scraping_enabled=True,
            active=True,
        ),
        DimCompetitor(
            competitor_name="Staples.nl",
            base_url="https://www.staples.nl",
            competitor_type="online",
            default_relevance_score=0.70,
            channel_relevance={"B2B": 0.8, "B2C": 0.7},
            scraping_enabled=False,
            active=True,
        ),
        DimCompetitor(
            competitor_name="Bol.com (kantoor)",
            base_url="https://www.bol.com",
            competitor_type="marketplace",
            default_relevance_score=0.55,
            channel_relevance={"B2B": 0.4, "B2C": 0.9},
            scraping_enabled=False,
            active=True,
        ),
    ]
    db.add_all(concurrenten)
    db.commit()
    print(f"Inserted {len(concurrenten)} competitors.")

# Haal IDs op
c_map = {c.competitor_name: c.competitor_id for c in db.query(DimCompetitor).all()}
c_printshop = c_map.get("Printshop.nl")
c_goedkoop = c_map.get("GoedkoopToner.nl")
c_officemax = c_map.get("OfficeMax.nl")


# ─── competitor_scrape_config ──────────────────────────────────────────────
if db.query(CompetitorScrapeConfig).count() > 0:
    print("CompetitorScrapeConfig already exists — skipping.")
else:
    configs = [
        CompetitorScrapeConfig(
            competitor_id=c_printshop,
            page_type="product",
            url_pattern="https://www.printshop.nl/toner/hp-ce285a",
            title_selector="h1.product-title",
            price_selector=".price-current",
            stock_selector=".stock-indicator",
            delivery_selector=".delivery-info",
            ean_selector=".product-ean",
            scrape_method="requests",
            requests_per_minute=12,
            active=True,
        ),
        CompetitorScrapeConfig(
            competitor_id=c_goedkoop,
            page_type="product",
            url_pattern="https://www.goedkooptoner.nl/hp-85a-toner",
            title_selector="h1",
            price_selector=".our-price",
            stock_selector=".availability",
            delivery_selector=".shipping-info",
            scrape_method="requests",
            requests_per_minute=6,
            active=True,
        ),
        CompetitorScrapeConfig(
            competitor_id=c_officemax,
            page_type="product",
            url_pattern="https://www.officemax.nl/producten/toner/hp-85a",
            title_selector="h1.pdp-title",
            price_selector=".price-box .price",
            stock_selector=".stock-label",
            delivery_selector=".delivery-promise",
            scrape_method="requests",
            requests_per_minute=8,
            active=True,
        ),
    ]
    db.add_all(configs)
    db.commit()
    print(f"Inserted {len(configs)} scrape configs.")


# ─── fact_scrape_result ────────────────────────────────────────────────────
if db.query(FactScrapeResult).count() > 0:
    print("FactScrapeResult already exists — skipping.")
else:
    scrapes = [
        FactScrapeResult(
            competitor_id=c_printshop,
            product_url="https://www.printshop.nl/toner/hp-ce285a",
            scraped_at=datetime.utcnow() - timedelta(hours=2),
            scrape_status="SCRAPE_SUCCESS",
            product_title="HP 85A CE285A Zwart Toner Cartridge",
            brand="HP",
            ean="0884962775356",
            mpn="CE285A",
            price_inc_vat=235.00,
            shipping_cost=0.00,
            total_price_inc_vat=235.00,
            stock_status="op_voorraad",
            delivery_text="Voor 23:00 besteld, morgen in huis",
            delivery_days=1,
            pack_size="1st",
            seller_name="Printshop.nl",
        ),
        FactScrapeResult(
            competitor_id=c_goedkoop,
            product_url="https://www.goedkooptoner.nl/hp-85a-toner",
            scraped_at=datetime.utcnow() - timedelta(hours=3),
            scrape_status="SCRAPE_SUCCESS",
            product_title="HP CE285A 85A Zwart Toner",
            brand="HP",
            ean="0884962775356",
            mpn="CE285A",
            price_inc_vat=199.00,
            shipping_cost=4.95,
            total_price_inc_vat=203.95,
            stock_status="op_voorraad",
            delivery_text="2-3 werkdagen",
            delivery_days=3,
            pack_size="1st",
            seller_name="GoedkoopToner.nl",
        ),
        FactScrapeResult(
            competitor_id=c_officemax,
            product_url="https://www.officemax.nl/producten/toner/hp-85a",
            scraped_at=datetime.utcnow() - timedelta(hours=1),
            scrape_status="SCRAPE_SUCCESS",
            product_title="HP 85A CE285A Toner Cartridge Zwart",
            brand="HP",
            ean="0884962775356",
            mpn="CE285A",
            price_inc_vat=210.00,
            shipping_cost=0.00,
            total_price_inc_vat=210.00,
            stock_status="niet_op_voorraad",
            delivery_text="Tijdelijk niet op voorraad",
            delivery_days=None,
            pack_size="1st",
            seller_name="OfficeMax.nl",
        ),
        # Extra scrapes voor potloden (hoge match confidence demo)
        FactScrapeResult(
            competitor_id=c_printshop,
            product_url="https://www.printshop.nl/potloden/staedtler-hb",
            scraped_at=datetime.utcnow() - timedelta(hours=4),
            scrape_status="SCRAPE_SUCCESS",
            product_title="Staedtler HB Potloden 12 stuks",
            brand="Staedtler",
            ean="4007817326015",
            mpn="120-HB",
            price_inc_vat=4.95,
            shipping_cost=0.00,
            total_price_inc_vat=4.95,
            stock_status="op_voorraad",
            delivery_text="Op werkdagen voor 23:00 besteld, morgen geleverd",
            delivery_days=1,
            pack_size="12st",
        ),
        # Ordner (lagere PCIS ondanks aanbodoverlap)
        FactScrapeResult(
            competitor_id=c_officemax,
            product_url="https://www.officemax.nl/ordners/leitz-180",
            scraped_at=datetime.utcnow() - timedelta(hours=5),
            scrape_status="SCRAPE_SUCCESS",
            product_title="Leitz 180 graden ordner A4 zwart",
            brand="Leitz",
            ean="4002432384006",
            mpn="1050-95-95",
            price_inc_vat=12.50,
            shipping_cost=0.00,
            total_price_inc_vat=12.50,
            stock_status="op_voorraad",
            delivery_text="1-2 werkdagen",
            delivery_days=2,
            pack_size="1st",
        ),
        FactScrapeResult(
            competitor_id=c_goedkoop,
            product_url="https://www.goedkooptoner.nl/hp-ce278a",
            scraped_at=datetime.utcnow() - timedelta(hours=6),
            scrape_status="SCRAPE_FAILED_SELECTOR_MISSING",
            error_message="title_selector leeg: geen .product-title gevonden",
        ),
    ]
    db.add_all(scrapes)
    db.commit()
    print(f"Inserted {len(scrapes)} scrape results.")


# ─── Haal toner-SKU op voor koppeling ──────────────────────────────────────
# Zoek een toner-SKU in dim_product
toner_sku = db.query(DimProduct).filter(
    DimProduct.product_name.ilike("%toner%")
).first()
potlood_sku = db.query(DimProduct).filter(
    DimProduct.product_name.ilike("%potlood%")
).first()
ordner_sku = db.query(DimProduct).filter(
    DimProduct.product_name.ilike("%ordner%")
).first()


# ─── fact_competitor_offer_daily ───────────────────────────────────────────
if db.query(FactCompetitorOfferDaily).count() > 0:
    print("FactCompetitorOfferDaily already exists — skipping.")
elif toner_sku:
    aanbiedingen = [
        # Toner — vandaag
        FactCompetitorOfferDaily(
            date=vandaag,
            own_sku_id=toner_sku.sku_id,
            competitor_id=c_printshop,
            competitor_sku="CE285A-PS",
            product_url="https://www.printshop.nl/toner/hp-ce285a",
            competitor_price_inc_vat=235.00,
            shipping_cost=0.00,
            total_price_inc_vat=235.00,
            in_stock=True,
            delivery_days=1,
            match_type="EXACT_MATCH",
            match_confidence=0.98,
            pack_size="1st",
            source="scraper",
        ),
        FactCompetitorOfferDaily(
            date=vandaag,
            own_sku_id=toner_sku.sku_id,
            competitor_id=c_goedkoop,
            competitor_sku="CE285A-GK",
            product_url="https://www.goedkooptoner.nl/hp-85a-toner",
            competitor_price_inc_vat=199.00,
            shipping_cost=4.95,
            total_price_inc_vat=203.95,
            in_stock=True,
            delivery_days=3,
            match_type="STRONG_MATCH",
            match_confidence=0.82,
            pack_size="1st",
            source="scraper",
        ),
        FactCompetitorOfferDaily(
            date=vandaag,
            own_sku_id=toner_sku.sku_id,
            competitor_id=c_officemax,
            competitor_sku="CE285A-OM",
            product_url="https://www.officemax.nl/producten/toner/hp-85a",
            competitor_price_inc_vat=210.00,
            shipping_cost=0.00,
            total_price_inc_vat=210.00,
            in_stock=False,
            delivery_days=None,
            match_type="EXACT_MATCH",
            match_confidence=0.99,
            pack_size="1st",
            source="scraper",
        ),
        # Toner — gisteren (voor trenddetectie)
        FactCompetitorOfferDaily(
            date=gisteren,
            own_sku_id=toner_sku.sku_id,
            competitor_id=c_printshop,
            competitor_sku="CE285A-PS",
            product_url="https://www.printshop.nl/toner/hp-ce285a",
            competitor_price_inc_vat=245.00,
            shipping_cost=0.00,
            total_price_inc_vat=245.00,
            in_stock=True,
            delivery_days=1,
            match_type="EXACT_MATCH",
            match_confidence=0.98,
            pack_size="1st",
            source="scraper",
        ),
        FactCompetitorOfferDaily(
            date=gisteren,
            own_sku_id=toner_sku.sku_id,
            competitor_id=c_goedkoop,
            competitor_sku="CE285A-GK",
            product_url="https://www.goedkooptoner.nl/hp-85a-toner",
            competitor_price_inc_vat=220.00,
            shipping_cost=4.95,
            total_price_inc_vat=224.95,
            in_stock=True,
            delivery_days=2,
            match_type="STRONG_MATCH",
            match_confidence=0.82,
            pack_size="1st",
            source="scraper",
        ),
        FactCompetitorOfferDaily(
            date=gisteren,
            own_sku_id=toner_sku.sku_id,
            competitor_id=c_officemax,
            competitor_sku="CE285A-OM",
            product_url="https://www.officemax.nl/producten/toner/hp-85a",
            competitor_price_inc_vat=215.00,
            shipping_cost=0.00,
            total_price_inc_vat=215.00,
            in_stock=True,      # gisteren was OfficeMax nog op voorraad
            delivery_days=2,
            match_type="EXACT_MATCH",
            match_confidence=0.99,
            pack_size="1st",
            source="scraper",
        ),
    ]
    db.add_all(aanbiedingen)
    db.commit()
    print(f"Inserted {len(aanbiedingen)} competitor offer daily records.")
else:
    print("Geen toner-SKU gevonden — fact_competitor_offer_daily overgeslagen.")


# ─── product_match ─────────────────────────────────────────────────────────
if db.query(ProductMatch).count() > 0:
    print("ProductMatch already exists — skipping.")
else:
    matches = []
    if toner_sku:
        matches += [
            ProductMatch(
                own_sku_id=toner_sku.sku_id,
                competitor_id=c_printshop,
                competitor_sku="CE285A-PS",
                competitor_url="https://www.printshop.nl/toner/hp-ce285a",
                match_type="EXACT_MATCH",
                match_confidence=0.98,
                match_reason="MATCH_EXACT_EAN",
                pack_size_warning=False,
                manual_override=False,
                approved_by="analyst",
                approved_at=datetime.utcnow() - timedelta(days=1),
                active=True,
            ),
            ProductMatch(
                own_sku_id=toner_sku.sku_id,
                competitor_id=c_goedkoop,
                competitor_sku="CE285A-GK",
                competitor_url="https://www.goedkooptoner.nl/hp-85a-toner",
                match_type="STRONG_MATCH",
                match_confidence=0.82,
                match_reason="MATCH_STRONG_TITLE_BRAND",
                pack_size_warning=False,
                manual_override=False,
                approved_by=None,  # wacht op goedkeuring
                active=True,
            ),
            ProductMatch(
                own_sku_id=toner_sku.sku_id,
                competitor_id=c_officemax,
                competitor_sku="CE285A-OM",
                competitor_url="https://www.officemax.nl/producten/toner/hp-85a",
                match_type="EXACT_MATCH",
                match_confidence=0.99,
                match_reason="MATCH_EXACT_EAN",
                pack_size_warning=False,
                manual_override=False,
                approved_by="pricing_manager",
                approved_at=datetime.utcnow() - timedelta(days=2),
                active=True,
            ),
        ]
    if potlood_sku:
        matches.append(
            ProductMatch(
                own_sku_id=potlood_sku.sku_id,
                competitor_id=c_printshop,
                competitor_sku="120-HB-PS",
                competitor_url="https://www.printshop.nl/potloden/staedtler-hb",
                match_type="EXACT_MATCH",
                match_confidence=0.97,
                match_reason="MATCH_EXACT_EAN",
                pack_size_warning=False,
                manual_override=False,
                approved_by="analyst",
                approved_at=datetime.utcnow() - timedelta(days=3),
                active=True,
            )
        )
    if ordner_sku:
        matches.append(
            ProductMatch(
                own_sku_id=ordner_sku.sku_id,
                competitor_id=c_officemax,
                competitor_sku="1050-95-95-OM",
                competitor_url="https://www.officemax.nl/ordners/leitz-180",
                match_type="PROBABLE_MATCH",
                match_confidence=0.61,
                match_reason="MATCH_STRONG_TITLE_BRAND",
                pack_size_warning=False,
                manual_override=False,
                approved_by=None,
                active=True,
            )
        )
    if matches:
        db.add_all(matches)
        db.commit()
        print(f"Inserted {len(matches)} product matches.")
    else:
        print("Geen SKU's gevonden voor product matches.")


# ─── fact_monitoring_alert ─────────────────────────────────────────────────
if db.query(FactMonitoringAlert).count() > 0:
    print("FactMonitoringAlert already exists — skipping.")
else:
    alerts = []
    if toner_sku:
        alerts += [
            # Concurrent B daling: €220 → €199 — maar lage CSRS → NIET volgen
            FactMonitoringAlert(
                date=vandaag,
                own_sku_id=toner_sku.sku_id,
                competitor_id=c_goedkoop,
                alert_type="COMPETITOR_PRICE_DROPPED",
                severity="hoog",
                message="GoedkoopToner.nl prijs gedaald met 9.5% (van €220.00 naar €199.00)",
                resolved=False,
            ),
            FactMonitoringAlert(
                date=vandaag,
                own_sku_id=toner_sku.sku_id,
                competitor_id=c_goedkoop,
                alert_type="LOW_PRICE_LOW_STOCK_RELIABILITY",
                severity="middel",
                message="GoedkoopToner.nl: lage prijs €199.00 maar CSRS laag (0.31) — niet volgen als referentie",
                resolved=False,
            ),
            # Concurrent C uit voorraad gegaan
            FactMonitoringAlert(
                date=vandaag,
                own_sku_id=toner_sku.sku_id,
                competitor_id=c_officemax,
                alert_type="COMPETITOR_OUT_OF_STOCK",
                severity="laag",
                message="OfficeMax.nl is uit voorraad gegaan voor HP CE285A",
                resolved=False,
            ),
            # Concurrent A prijs gedaald (gisteren €245 → nu €235)
            FactMonitoringAlert(
                date=vandaag,
                own_sku_id=toner_sku.sku_id,
                competitor_id=c_printshop,
                alert_type="COMPETITOR_PRICE_DROPPED",
                severity="middel",
                message="Printshop.nl prijs gedaald met 4.1% (van €245.00 naar €235.00) — hoge CSRS, relevante signaal",
                resolved=False,
            ),
            # Prijsuitbijter GoedkoopToner
            FactMonitoringAlert(
                date=vandaag,
                own_sku_id=toner_sku.sku_id,
                competitor_id=c_goedkoop,
                alert_type="COMPETITOR_PRICE_OUTLIER",
                severity="middel",
                message="GoedkoopToner.nl prijs €199.00 is statistisch afwijkend van markt (mediaan €222.50)",
                resolved=False,
            ),
        ]

    # Extra alerts voor andere SKUs
    alle_skus = db.query(DimProduct).limit(5).all()
    for sku in alle_skus[:3]:
        if sku.sku_id != (toner_sku.sku_id if toner_sku else ""):
            alerts.append(
                FactMonitoringAlert(
                    date=vandaag - timedelta(days=1),
                    own_sku_id=sku.sku_id,
                    competitor_id=c_printshop,
                    alert_type="COMPETITOR_PRICE_INCREASED",
                    severity="laag",
                    message=f"Printshop.nl prijs gestegen voor {sku.product_name[:40]}",
                    resolved=True,
                )
            )

    if alerts:
        db.add_all(alerts)
        db.commit()
        print(f"Inserted {len(alerts)} monitoring alerts.")


# ─── price_execution_job + lines ──────────────────────────────────────────
if db.query(PriceExecutionJob).count() > 0:
    print("PriceExecutionJob already exists — skipping.")
else:
    # Demo job: CSV export van 3 goedgekeurde adviezen
    job = PriceExecutionJob(
        created_at=datetime.utcnow() - timedelta(days=1),
        created_by="pricing_manager",
        execution_mode="MANUAL_EXPORT",
        status="geëxporteerd",
        approved_count=3,
        rejected_count=1,
        export_file_path=f"/exports/prijswijzigingen_{gisteren}.csv",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Haal enkele goedgekeurde aanbevelingen op
    recs = db.query(FactPricingRecommendationDaily).filter(
        FactPricingRecommendationDaily.approval_status == "approved"
    ).limit(4).all()

    if recs:
        for i, rec in enumerate(recs):
            prod = db.query(DimProduct).filter(DimProduct.sku_id == rec.sku_id).first()
            oud = float(rec.current_price) if rec.current_price else 100.0
            nieuw = float(rec.recommended_price) if rec.recommended_price else oud * 1.02
            pct = round((nieuw - oud) / oud * 100, 2)
            status = "afgewezen_guardrail" if i == 3 else "goedgekeurd"
            line = PriceExecutionLine(
                job_id=job.job_id,
                sku_id=rec.sku_id,
                old_price=oud,
                new_price=nieuw if status == "goedgekeurd" else oud,
                change_pct=pct if status == "goedgekeurd" else 0,
                status=status,
                reason_code=rec.reason_code,
                rollback_price=oud,
            )
            db.add(line)
        db.commit()
        print(f"Inserted 1 execution job with {min(len(recs), 4)} lines.")
    else:
        print("Geen goedgekeurde aanbevelingen — geen execution lines.")

    # Tweede job: dry run van vandaag
    job2 = PriceExecutionJob(
        created_at=datetime.utcnow() - timedelta(hours=2),
        created_by="analyst",
        execution_mode="DRY_RUN",
        status="aangemaakt",
        approved_count=5,
        rejected_count=2,
    )
    db.add(job2)
    db.commit()
    print("Inserted dry run job.")


db.close()
print("\nKlaar — alle module-backfill data geladen.")
