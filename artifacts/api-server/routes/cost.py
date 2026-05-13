"""Cost Intelligence routes — /api/kosten/*"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from typing import Any, Dict

from database import get_db
from auth import get_current_user
from models import (
    FactCostDaily, FactMarketingCostDaily,
    FactOperationalComplexityDaily, DimProduct,
)
from engine.cost_engine import get_cost_dashboard, compute_cost_record
from engine.marketing_efficiency import compute_marketing_record
from engine.operational_complexity import compute_ocs_record

router = APIRouter(prefix="/api/kosten", tags=["kosten"])


@router.get("")
def get_kosten_dashboard(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Volledig kostendashboard: KPI's + SKU overzicht."""
    return get_cost_dashboard(db)


@router.get("/sku/{sku_id}")
def get_kosten_sku(
    sku_id: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Kosten detail voor één SKU inclusief marketing en operationele complexiteit."""
    # Meest recente kosten record
    cost_rec = (
        db.query(FactCostDaily)
        .filter(FactCostDaily.sku_id == sku_id)
        .order_by(FactCostDaily.date.desc())
        .first()
    )
    mkt_rec = (
        db.query(FactMarketingCostDaily)
        .filter(FactMarketingCostDaily.sku_id == sku_id)
        .order_by(FactMarketingCostDaily.date.desc())
        .first()
    )
    ocs_rec = (
        db.query(FactOperationalComplexityDaily)
        .filter(FactOperationalComplexityDaily.sku_id == sku_id)
        .order_by(FactOperationalComplexityDaily.date.desc())
        .first()
    )

    # Fall-back: bereken live als geen data
    prod = db.query(DimProduct).filter(DimProduct.sku_id == sku_id).first()
    if not prod:
        raise HTTPException(404, "SKU niet gevonden")

    sp = float(prod.current_price or prod.cost_price or 1)
    cp = float(prod.cost_price or sp * 0.6)

    if not cost_rec:
        cost_data = compute_cost_record(sku_id, prod.product_name, prod.category, cp, sp)
    else:
        cost_data = {
            "sku_id": cost_rec.sku_id,
            "sku_name": cost_rec.sku_name,
            "categorie": cost_rec.category,
            "datum": str(cost_rec.date),
            "inkoopkosten": float(cost_rec.purchase_cost or 0),
            "transportkosten": float(cost_rec.transport_cost or 0),
            "dropshipping": float(cost_rec.dropshipping_cost or 0),
            "fulfilment": float(cost_rec.fulfilment_cost or 0),
            "verpakking": float(cost_rec.packaging_cost or 0),
            "personeel": float(cost_rec.labour_cost or 0),
            "marketplace_fee": float(cost_rec.marketplace_fee or 0),
            "retouren": float(cost_rec.return_cost or 0),
            "overhead": float(cost_rec.overhead_cost or 0),
            "totale_directe_kosten": float(cost_rec.total_direct_cost or 0),
            "totale_indirecte_kosten": float(cost_rec.total_indirect_cost or 0),
            "totale_kosten": float(cost_rec.total_cost or 0),
            "verkoopprijs": float(cost_rec.selling_price or 0),
            "bruto_marge": float(cost_rec.gross_margin or 0),
            "netto_marge": float(cost_rec.net_margin or 0),
            "netto_marge_pct": float(cost_rec.net_margin_pct or 0),
            "signaal": cost_rec.cost_signal,
            "signaal_nl": cost_rec.cost_signal_nl,
        }

    mkt_data = {}
    if mkt_rec:
        mkt_data = {
            "seo_kosten": float(mkt_rec.seo_cost or 0),
            "sea_kosten": float(mkt_rec.sea_cost or 0),
            "totale_marketing": float(mkt_rec.total_marketing_cost or 0),
            "cac": float(mkt_rec.cac or 0),
            "roas": float(mkt_rec.roas or 0),
            "seo_efficiency": float(mkt_rec.seo_efficiency or 0),
            "sea_efficiency": float(mkt_rec.sea_efficiency or 0),
            "marketing_dependency": float(mkt_rec.marketing_dependency_score or 0),
            "marge_na_marketing": float(mkt_rec.margin_after_marketing or 0),
            "contribution_margin_pct": float(mkt_rec.contribution_margin_pct or 0),
            "signaal": mkt_rec.marketing_signal,
            "signaal_nl": mkt_rec.marketing_signal_nl,
        }

    ocs_data = {}
    if ocs_rec:
        ocs_data = {
            "ocs_score": float(ocs_rec.operational_complexity_score or 0),
            "ocs_label": ocs_rec.ocs_label,
            "pick_time": float(ocs_rec.pick_time_score or 0),
            "packaging_time": float(ocs_rec.packaging_time_score or 0),
            "retourdruk": float(ocs_rec.return_pressure or 0),
            "klantenservice": float(ocs_rec.customer_service_load or 0),
            "handling": float(ocs_rec.handling_complexity or 0),
            "dropship": float(ocs_rec.dropship_management or 0),
            "supplier": float(ocs_rec.supplier_management or 0),
            "foutgevoeligheid": float(ocs_rec.error_sensitivity or 0),
            "personeelskosten_per_eenheid": float(ocs_rec.labour_cost_per_unit or 0),
            "aanbeveling": ocs_rec.recommended_action,
        }

    return {
        "sku_id": sku_id,
        "naam": prod.product_name,
        "categorie": prod.category,
        "kosten": cost_data,
        "marketing": mkt_data,
        "operationeel": ocs_data,
    }


@router.get("/categorie/{category}")
def get_kosten_categorie(
    category: str,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Kostenanalyse geaggregeerd per categorie."""
    latest = db.query(func.max(FactCostDaily.date)).scalar() or date.today()
    recs = (
        db.query(FactCostDaily)
        .filter(
            FactCostDaily.date == latest,
            FactCostDaily.category.ilike(f"%{category}%"),
        )
        .all()
    )
    if not recs:
        raise HTTPException(404, f"Geen kosten data voor categorie: {category}")

    def avg(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs]
        return round(sum(vals) / len(vals), 4) if vals else 0

    return {
        "categorie": category,
        "datum": str(latest),
        "totaal_skus": len(recs),
        "gemiddelde_netto_marge_pct": avg("net_margin_pct"),
        "gemiddelde_totale_kosten": avg("total_cost"),
        "gemiddelde_verkoopprijs": avg("selling_price"),
        "kostenverdeling": {
            "inkoop": avg("purchase_cost"),
            "transport": avg("transport_cost"),
            "fulfilment": avg("fulfilment_cost"),
            "verpakking": avg("packaging_cost"),
            "personeel": avg("labour_cost"),
            "marketplace": avg("marketplace_fee"),
            "retouren": avg("return_cost"),
            "overhead": avg("overhead_cost"),
        },
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "netto_marge_pct": float(r.net_margin_pct or 0),
                "signaal": r.cost_signal,
            }
            for r in sorted(recs, key=lambda x: float(x.net_margin_pct or 0))
        ],
    }


@router.get("/marketing")
def get_marketing_overview(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Marketing efficiency overzicht voor alle SKU's."""
    latest = db.query(func.max(FactMarketingCostDaily.date)).scalar() or date.today()
    recs = (
        db.query(FactMarketingCostDaily)
        .filter(FactMarketingCostDaily.date == latest)
        .all()
    )

    def avg(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 4) if vals else 0

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "gemiddelde_roas": avg("roas"),
        "gemiddelde_cac": avg("cac"),
        "gemiddelde_seo_efficiency": avg("seo_efficiency"),
        "gemiddelde_sea_efficiency": avg("sea_efficiency"),
        "totale_marketing_kosten": round(sum(float(r.total_marketing_cost or 0) for r in recs), 2),
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "roas": float(r.roas or 0),
                "cac": float(r.cac or 0),
                "seo_efficiency": float(r.seo_efficiency or 0),
                "sea_efficiency": float(r.sea_efficiency or 0),
                "marketing_dependency": float(r.marketing_dependency_score or 0),
                "marge_na_marketing": float(r.margin_after_marketing or 0),
                "contribution_margin_pct": float(r.contribution_margin_pct or 0),
                "signaal": r.marketing_signal,
                "signaal_nl": r.marketing_signal_nl,
            }
            for r in sorted(recs, key=lambda x: float(x.roas or 0))
        ],
    }


@router.get("/operationeel")
def get_operationele_complexiteit(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> Any:
    """Operationele complexiteitsscores (OCS/ABC) voor alle SKU's."""
    latest = db.query(func.max(FactOperationalComplexityDaily.date)).scalar() or date.today()
    recs = (
        db.query(FactOperationalComplexityDaily)
        .filter(FactOperationalComplexityDaily.date == latest)
        .order_by(FactOperationalComplexityDaily.operational_complexity_score.desc())
        .all()
    )

    def avg(attr):
        vals = [float(getattr(r, attr) or 0) for r in recs]
        return round(sum(vals) / len(vals), 4) if vals else 0

    kritiek = [r for r in recs if r.ocs_label == "KRITIEK"]
    hoog = [r for r in recs if r.ocs_label == "HOOG"]

    return {
        "datum": str(latest),
        "totaal_skus": len(recs),
        "gemiddelde_ocs": avg("operational_complexity_score"),
        "kritiek_count": len(kritiek),
        "hoog_count": len(hoog),
        "skus": [
            {
                "sku_id": r.sku_id,
                "naam": r.sku_name,
                "categorie": r.category,
                "ocs_score": float(r.operational_complexity_score or 0),
                "ocs_label": r.ocs_label,
                "pick_time": float(r.pick_time_score or 0),
                "packaging_time": float(r.packaging_time_score or 0),
                "retourdruk": float(r.return_pressure or 0),
                "klantenservice": float(r.customer_service_load or 0),
                "handling": float(r.handling_complexity or 0),
                "personeelskosten": float(r.labour_cost_per_unit or 0),
                "aanbeveling": r.recommended_action,
            }
            for r in recs
        ],
    }
