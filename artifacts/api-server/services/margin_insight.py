"""Confirmed DRS evidence, durable asynchronous pricing runs and honest margins."""
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import threading

from fastapi import HTTPException
from sqlalchemy import func
import models

logger = logging.getLogger(__name__)
RUN_KIND = "drs_margin"
# Interrupted daemon work becomes visibly failed instead of running forever.
RUN_TIMEOUT = timedelta(hours=2)


def price_version(db, shop_id):
    P = models.DimProduct
    rows = db.query(P.sku_id, P.current_price, P.cost_price, P.price_incl_vat,
                    P.import_source, P.strategy_type, P.min_price, P.max_price,
                    P.lifecycle_status).filter(P.shop_id == shop_id).order_by(P.sku_id).all()
    return hashlib.sha256(json.dumps([list(r) for r in rows], default=str).encode()).hexdigest()


def recommendation_watermark(db, shop_id):
    R = models.FactPricingRecommendationDaily
    return db.query(func.max(R.id)).filter(R.shop_id == shop_id).scalar() or 0


def run_query(db, shop_id):
    return db.query(models.ModelRun).filter(
        models.ModelRun.run_metadata["kind"].as_string() == RUN_KIND,
        models.ModelRun.run_metadata["shop_id"].as_integer() == shop_id)


def run_dict(run):
    if not run:
        return None
    return {"id": run.id, "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "error_message": run.error_message,
            "source_version": (run.run_metadata or {}).get("source_version")}


def latest_run(db, shop_id, *, commit_expiry=True):
    run = run_query(db, shop_id).order_by(models.ModelRun.id.desc()).first()
    if run and run.status == "running" and run.started_at < datetime.utcnow() - RUN_TIMEOUT:
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        run.error_message = "Herberekening onderbroken of tijdslimiet overschreden; start opnieuw."
        if commit_expiry:
            db.commit()
        else:
            db.flush()
    return run


def source_status(db, shop_id):
    stages = db.query(models.DrsDailyStage).filter(
        models.DrsDailyStage.shop_id == shop_id).order_by(
            models.DrsDailyStage.created_at.desc(), models.DrsDailyStage.id.desc()).all()
    def state(s):
        if s is None:
            return "none"
        if s.status == "confirmed":
            return "confirmed"
        if s.mapping_result:
            return "mappings_only"
        return "blocked" if s.status == "blocked" else "preview"
    confirmed = [s for s in stages if s.status == "confirmed"]
    # Confirmation order, not upload order, when confirmation evidence exists.
    confirmed.sort(key=lambda s: (s.result or {}).get("confirmed_at") or s.created_at.isoformat(),
                   reverse=True)
    stage = confirmed[0] if confirmed else (stages[0] if stages else None)
    preview = stage.preview if stage else {}
    fingerprint = [(s.id, s.result, s.preview.get("period_start"), s.preview.get("period_end"))
                   for s in confirmed]
    version = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, default=str).encode()).hexdigest() if confirmed else None
    F = models.FactSalesDaily
    q = db.query(func.count(F.id)).filter(F.shop_id == shop_id, F.source == "DRS_DAILY")
    start, end = preview.get("period_start"), preview.get("period_end")
    if start and end:
        q = q.filter(F.date.between(date.fromisoformat(start), date.fromisoformat(end)))
    return {"status": state(stage), "latest_attempt_status": state(stages[0] if stages else None),
            "stage_id": stage.id if stage else None, "period_start": start, "period_end": end,
            "confirmed_at": (stage.result or {}).get("confirmed_at") if confirmed else None,
            "sales_rows": q.scalar(), "source_version": version}


def start_recalculation(db, shop_id, username):
    # Persisted shop row serializes admission across processes, not just threads.
    db.query(models.DimShop).filter(models.DimShop.id == shop_id).with_for_update().one()
    source = source_status(db, shop_id)
    if source["status"] != "confirmed":
        raise HTTPException(409, "Bevestig eerst DRS-dagverkoop voor deze winkel.")
    # Do not release the admission lock while expiring an interrupted attempt.
    run = latest_run(db, shop_id, commit_expiry=False)
    if run and run.status == "running":
        db.commit()
        return run_dict(run)
    if (run and run.status == "completed"
            and (run.run_metadata or {}).get("source_version") == source["source_version"]
            and (run.run_metadata or {}).get("price_version") == price_version(db, shop_id)
            and (run.run_metadata or {}).get("recommendation_watermark") == recommendation_watermark(db, shop_id)):
        # Only idempotent while the published snapshot still exists unchanged.
        ids = (run.run_metadata or {}).get("recommendation_ids", [])
        count = db.query(models.FactPricingRecommendationDaily).filter(
            models.FactPricingRecommendationDaily.shop_id == shop_id,
            models.FactPricingRecommendationDaily.model_version == run.model_version,
            models.FactPricingRecommendationDaily.id.in_(ids)).count()
        if count == len(ids):
            db.commit()
            return run_dict(run)
    run = models.ModelRun(status="running", started_at=datetime.utcnow(),
                          model_version="v1.0.0", run_metadata={
                              "kind": RUN_KIND, "shop_id": shop_id, **source,
                              "requested_by": username, "price_version": price_version(db, shop_id)})
    db.add(run)
    db.flush()
    # A unique version binds recommendations to ONE snapshot, without schema drift.
    run.model_version = f"v1.0.0-drs-{run.id}"
    db.add(models.AuditLog(entity_type="model_run", entity_id=str(run.id),
                           action="drs_margin_recalculate", performed_by=username,
                           details=f"shop_id={shop_id}; source_version={source['source_version']}"))
    db.commit()
    result = run_dict(run)
    try:
        threading.Thread(target=execute_recalculation, args=(run.id, shop_id),
                         name=f"drs-margin-{run.id}", daemon=True).start()
    except Exception:
        run.status, run.error_message = "failed", "Achtergrondtaak kon niet starten."
        run.completed_at = datetime.utcnow()
        db.commit()
        result = run_dict(run)
    return result


def execute_recalculation(run_id, shop_id, session_factory=None):
    from database import BackgroundSessionLocal
    from engine.pricing_engine import run_pricing_engine
    db = (session_factory or BackgroundSessionLocal)()
    try:
        from services.product_identity import sales_lock
        sales_lock(db, shop_id)
        run = run_query(db, shop_id).filter(models.ModelRun.id == run_id).one()
        if run.status != "running":
            return
        evidence = dict(run.run_metadata)
        if source_status(db, shop_id)["source_version"] != evidence["source_version"]:
            raise ValueError("Bevestigde verkoopbron gewijzigd; start opnieuw.")
        evidence["price_version"] = price_version(db, shop_id)
        period = (date.fromisoformat(evidence["period_start"]),
                  date.fromisoformat(evidence["period_end"]))
        processed, skipped = run_pricing_engine(
            db, shop_id=shop_id, sales_period=period, model_version=run.model_version)
        if source_status(db, shop_id)["source_version"] != evidence["source_version"]:
            raise ValueError("Verkoop gewijzigd tijdens herberekening; start opnieuw.")
        if price_version(db, shop_id) != evidence["price_version"]:
            raise ValueError("Catalogusprijzen gewijzigd tijdens herberekening; start opnieuw.")
        R = models.FactPricingRecommendationDaily
        evidence["recommendation_ids"] = [r[0] for r in db.query(R.id).filter(
            R.shop_id == shop_id, R.model_version == run.model_version)]
        evidence["recommendation_watermark"] = recommendation_watermark(db, shop_id)
        changed = run_query(db, shop_id).filter(models.ModelRun.id == run_id,
            models.ModelRun.status == "running").update({
                models.ModelRun.run_metadata: evidence, models.ModelRun.status: "completed",
                models.ModelRun.completed_at: datetime.utcnow(),
                models.ModelRun.skus_processed: processed, models.ModelRun.skus_skipped: skipped},
                synchronize_session=False)
        if not changed:
            raise ValueError("Run is niet meer actief.")
        db.commit()
    except Exception:
        logger.exception("DRS margin recalculation failed: run=%s shop=%s", run_id, shop_id)
        db.rollback()
        run = run_query(db, shop_id).filter(models.ModelRun.id == run_id).one()
        run.status, run.completed_at = "failed", datetime.utcnow()
        # Do not return SQL/credentials/data from arbitrary exception strings.
        run.error_message = "Herberekening mislukt; adviezen niet gepubliceerd. Probeer opnieuw of raadpleeg beheer."
        db.commit()
    finally:
        db.close()


def insight(db, shop_id, sku_filter=None, period_start=None, period_end=None,
            comparison_start=None, comparison_end=None):
    source, run = source_status(db, shop_id), latest_run(db, shop_id)
    evidence = (run.run_metadata or {}) if run else {}
    P, R, F = models.DimProduct, models.FactPricingRecommendationDaily, models.FactSalesDaily
    def filtered(q, col):
        return q.filter(col.in_(sku_filter)) if sku_filter is not None else q
    products = filtered(db.query(P).filter(P.shop_id == shop_id,
                         P.lifecycle_status != "discontinued"), P.sku_id).all()
    recs = filtered(db.query(R).filter(R.shop_id == shop_id,
                    R.model_version == (run.model_version if run else None),
                    R.id.in_(evidence.get("recommendation_ids", []))), R.sku_id).all()
    volume_start, volume_end = evidence.get("period_start"), evidence.get("period_end")
    volume_skus = set()
    if volume_start and volume_end:
        C = models.SalesDailyClaim
        days = (date.fromisoformat(volume_end) - date.fromisoformat(volume_start)).days + 1
        volume_skus = {r[0] for r in filtered(db.query(C.sku_id).filter(
            C.shop_id == shop_id, C.source == "DRS_DAILY",
            C.date.between(date.fromisoformat(volume_start), date.fromisoformat(volume_end))),
            C.sku_id).group_by(C.sku_id).having(func.count(C.id) == days)}
    published_count = db.query(R.id).filter(R.shop_id == shop_id,
        R.model_version == (run.model_version if run else None),
        R.id.in_(evidence.get("recommendation_ids", []))).count()
    fresh = bool(run and run.status == "completed"
                 and evidence.get("source_version") == source["source_version"]
                 and evidence.get("price_version") == price_version(db, shop_id)
                 and evidence.get("recommendation_watermark") == recommendation_watermark(db, shop_id)
                 and published_count == len(evidence.get("recommendation_ids", [])))
    usable = [r for r in recs if r.expected_margin_uplift is not None
              and r.approval_status != "rejected" and r.override_price is None
              and r.safety_status != "blocked"]
    expected = {
        "status": ("fresh" if len(usable) == len(products) else "partial") if fresh else
                  ("stale" if run else "unavailable"),
        "margin_uplift": round(sum(float(r.expected_margin_uplift) for r in usable), 2) if fresh and usable else None,
        "revenue": round(sum(float(r.expected_revenue) for r in usable), 2) if fresh and usable else None,
        "margin": round(sum(float(r.expected_margin) for r in usable), 2) if fresh and usable else None,
        "horizon_days": 1, "volume_period_start": volume_start, "volume_period_end": volume_end,
        "volume_days": (date.fromisoformat(volume_end) - date.fromisoformat(volume_start)).days + 1 if volume_start and volume_end else None,
        "eligible_skus": len(products), "covered_skus": len(usable) if fresh else 0,
        "missing_volume_skus": sum(p.sku_id not in volume_skus for p in products),
        "missing_cost_skus": sum(p.cost_price is None or p.cost_price < 0 for p in products),
        "preserved_decision_skus": len({r[0] for r in filtered(db.query(R.sku_id).filter(
            R.shop_id == shop_id, (R.approval_status != "pending") | R.override_price.isnot(None)
            | R.override_reason.isnot(None) | R.source_decision_id.isnot(None)
            | R.processing_status.notin_(["niet_verwerkt"])), R.sku_id)}),
        "assumptions": [
            "Verwachting per kalenderdag, geen gerealiseerde winst; som van één adviessnapshot.",
            "Gemiddeld dagvolume = bevestigde DRS-eenheden / alle kalenderdagen in de bronperiode.",
            "Vraagelasticiteit -1,5; verwachte eenheden = max(0, dagvolume × (1 - 1,5 × prijswijziging)).",
            "Marge en omzet exclusief btw; actuele inkoopkosten zijn aannames, geen historische kosten.",
            "PriceShape-prijzen zijn inclusief btw: omrekening met de waargenomen DRS-verhouding incl/excl btw, aangenomen ongewijzigd. DRS-catalogusprijzen zijn exclusief btw. Onbekende btw-basis wordt uitgesloten.",
            "Concurrentprijzen tellen alleen mee bij bekende PriceShape-btw-basis en beschikbare DRS-omrekenfactor; substituten worden in dezelfde prijsbasis vergeleken.",
            "Negatief netto-volume (retoursemantiek niet geverifieerd) wordt niet voorspeld.",
            "Effect wordt na prijsveiligheidsregels berekend; geblokkeerde/afgewezen adviezen en menselijke overrides tellen niet mee.",
        ]}
    if bool(period_start) != bool(period_end) or bool(comparison_start) != bool(comparison_end):
        raise HTTPException(422, "Geef zowel begin- als einddatum op.")
    start = period_start or (date.fromisoformat(source["period_start"]) if source["period_start"] else None)
    end = period_end or (date.fromisoformat(source["period_end"]) if source["period_end"] else None)
    if start and end and start > end:
        raise HTTPException(422, "Begindatum ligt na einddatum.")
    cs = comparison_start or (start - timedelta(days=(end - start).days + 1) if start else None)
    ce = comparison_end or (start - timedelta(days=1) if start else None)
    if cs and ce and cs > ce:
        raise HTTPException(422, "Vergelijkingsbegindatum ligt na einddatum.")
    def actual_period(a, b):
        if not a or not b:
            return {"rows": 0, "missing": 0, "margin": None, "revenue": None}
        row = filtered(db.query(func.count(F.id), func.count(F.cost),
            func.sum(F.revenue), func.sum(F.revenue - F.cost), func.count(F.revenue)).filter(
                F.shop_id == shop_id, F.source == "DRS_DAILY", F.date.between(a, b)), F.sku_id).one()
        complete = row[0] > 0 and row[1] == row[0] and row[4] == row[0]
        return {"rows": row[0], "missing": row[0] - row[1],
                "margin": round(float(row[3]), 2) if complete else None,
                "revenue": float(row[2]) if row[2] is not None else None}
    actual, comparison = actual_period(start, end), actual_period(cs, ce)
    actual_out = {"period_start": start, "period_end": end, "comparison_start": cs,
        "comparison_end": ce, "revenue": actual["revenue"], "margin": actual["margin"],
        "comparison_margin": comparison["margin"], "margin_change":
        round(actual["margin"] - comparison["margin"], 2) if actual["margin"] is not None and comparison["margin"] is not None else None,
        "sales_rows": actual["rows"], "missing_cost_rows": actual["missing"],
        "comparison_sales_rows": comparison["rows"], "comparison_missing_cost_rows": comparison["missing"],
        "status": "complete" if actual["margin"] is not None and comparison["margin"] is not None else "incomplete",
        "explanation": "Historische marge = omzet excl. btw minus onderbouwde historische kosten. Ontbrekende kosten of vergelijkingsdata geven geen nul; actuele inkoopprijzen worden niet ingevuld."}
    return {"shop_id": shop_id, "source": source, "run": run_dict(run),
            "expected": expected, "actual": actual_out}