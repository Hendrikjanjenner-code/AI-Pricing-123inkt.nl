"""Export endpoint — approved recommendations as CSV (prijsexport)."""
import csv
import io
from datetime import date, datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/recommendations")
def export_recommendations(
    date_filter: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """
    Returns JSON metadata about the export.
    The actual CSV download is at /api/exports/recommendations/download.
    """
    q = db.query(models.FactPricingRecommendationDaily).filter(
        models.FactPricingRecommendationDaily.approval_status == "approved",
        models.FactPricingRecommendationDaily.exported == False,
    )
    if date_filter:
        try:
            d = date.fromisoformat(date_filter)
            q = q.filter(models.FactPricingRecommendationDaily.date == d)
        except ValueError:
            pass

    count = q.count()
    export_date = date_filter or datetime.utcnow().date().isoformat()
    filename = f"prijsexport_{export_date}.csv"

    return {
        "exported_count": count,
        "date": export_date,
        "download_url": f"/api/exports/recommendations/download?date={export_date}",
        "filename": filename,
    }


@router.get("/recommendations/download")
def download_recommendations_csv(
    date_filter: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    """Stream the approved recommendations as a CSV file."""
    q = db.query(models.FactPricingRecommendationDaily).filter(
        models.FactPricingRecommendationDaily.approval_status == "approved",
    )
    if date_filter:
        try:
            d = date.fromisoformat(date_filter)
            q = q.filter(models.FactPricingRecommendationDaily.date == d)
        except ValueError:
            pass

    recs = q.all()
    product_map = {
        p.sku_id: p
        for p in db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.in_([r.sku_id for r in recs])
        ).all()
    }

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "sku_id", "recommended_price", "min_price", "max_price",
        "reason_code", "confidence_score", "approved_by", "date"
    ])
    for r in recs:
        product = product_map.get(r.sku_id)
        writer.writerow([
            r.sku_id,
            float(r.override_price or r.recommended_price) if (r.override_price or r.recommended_price) else "",
            float(product.min_price) if product and product.min_price else "",
            float(product.max_price) if product and product.max_price else "",
            r.reason_code or "",
            round(float(r.confidence_score), 3) if r.confidence_score else "",
            r.approved_by or "",
            r.date.isoformat() if r.date else "",
        ])
        r.exported = True

    db.commit()
    output.seek(0)
    export_date = date_filter or datetime.utcnow().date().isoformat()
    filename = f"prijsexport_{export_date}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
