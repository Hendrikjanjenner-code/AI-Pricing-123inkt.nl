"""CSV upload endpoints for all data types."""
import io
import csv
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


async def _process_upload(
    file: UploadFile,
    upload_type: str,
    db: Session,
    user: models.User,
    processor,
) -> dict:
    """Generic upload processor that creates an import job."""
    job = models.ImportJob(
        upload_type=upload_type,
        filename=file.filename or "unknown.csv",
        status="processing",
        uploaded_by=user.username,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        content = await file.read()
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        processed, failed, warnings = processor(rows, db)
        job.rows_processed = processed
        job.rows_failed = failed
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()
        return {
            "job_id": job.id,
            "rows_processed": processed,
            "rows_failed": failed,
            "warnings": warnings,
            "message": f"Uploaded {processed} rows successfully",
        }
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=400, detail=f"Upload failed: {str(e)}")


def _process_products(rows, db: Session):
    processed, failed, warnings = 0, 0, []
    for row in rows:
        try:
            sku_id = row.get("sku_id") or row.get("SKU_ID")
            if not sku_id:
                failed += 1
                continue
            existing = db.query(models.DimProduct).filter(models.DimProduct.sku_id == sku_id).first()
            if existing:
                existing.product_name = row.get("product_name", existing.product_name)
                existing.brand = row.get("brand", existing.brand)
                existing.category = row.get("category", existing.category)
                existing.subcategory = row.get("subcategory", existing.subcategory)
                existing.strategy_type = row.get("strategy_type", existing.strategy_type)
                cost = row.get("cost_price")
                if cost:
                    existing.cost_price = float(cost)
                min_p = row.get("min_price")
                if min_p:
                    existing.min_price = float(min_p)
                max_p = row.get("max_price")
                if max_p:
                    existing.max_price = float(max_p)
            else:
                product = models.DimProduct(
                    sku_id=sku_id,
                    product_name=row.get("product_name", sku_id),
                    brand=row.get("brand"),
                    category=row.get("category"),
                    subcategory=row.get("subcategory"),
                    product_group=row.get("product_group"),
                    is_private_label=str(row.get("is_private_label", "false")).lower() in ("1", "true", "yes"),
                    is_a_brand=str(row.get("is_a_brand", "false")).lower() in ("1", "true", "yes"),
                    lifecycle_status=row.get("lifecycle_status", "active"),
                    strategy_type=row.get("strategy_type"),
                    cost_price=float(row["cost_price"]) if row.get("cost_price") else None,
                    min_price=float(row["min_price"]) if row.get("min_price") else None,
                    max_price=float(row["max_price"]) if row.get("max_price") else None,
                    current_price=float(row["current_price"]) if row.get("current_price") else None,
                )
                db.add(product)
            processed += 1
        except Exception as e:
            warnings.append(f"Row error: {str(e)}")
            failed += 1
    db.commit()
    return processed, failed, warnings


@router.get("")
def list_uploads(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    jobs = db.query(models.ImportJob).order_by(models.ImportJob.created_at.desc()).limit(50).all()
    return [
        {
            "id": j.id,
            "upload_type": j.upload_type,
            "filename": j.filename,
            "status": j.status,
            "rows_processed": j.rows_processed,
            "rows_failed": j.rows_failed,
            "error_message": j.error_message,
            "uploaded_by": j.uploaded_by,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@router.post("/products")
async def upload_products(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    return await _process_upload(file, "products", db, current_user, _process_products)


@router.post("/sales")
async def upload_sales(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    async def _inner():
        def _proc(rows, db):
            processed, failed, warnings = 0, 0, []
            from datetime import date
            for row in rows:
                try:
                    from models import FactSalesDaily
                    entry = FactSalesDaily(
                        date=date.fromisoformat(row["date"]),
                        sku_id=row["sku_id"],
                        units_sold=int(row.get("units_sold", 0)),
                        revenue=float(row["revenue"]) if row.get("revenue") else None,
                        cost=float(row["cost"]) if row.get("cost") else None,
                        margin=float(row["margin"]) if row.get("margin") else None,
                        margin_pct=float(row["margin_pct"]) if row.get("margin_pct") else None,
                    )
                    db.add(entry)
                    processed += 1
                except Exception as e:
                    warnings.append(str(e))
                    failed += 1
            db.commit()
            return processed, failed, warnings
        return await _process_upload(file, "sales", db, current_user, _proc)
    return await _inner()


@router.post("/prices")
async def upload_prices(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        from datetime import date
        for row in rows:
            try:
                entry = models.FactPriceDaily(
                    date=date.fromisoformat(row["date"]),
                    sku_id=row["sku_id"],
                    price=float(row["price"]) if row.get("price") else None,
                    cost_price=float(row["cost_price"]) if row.get("cost_price") else None,
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "prices", db, current_user, _proc)


@router.post("/competitor-prices")
async def upload_competitor_prices(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        from datetime import date
        for row in rows:
            try:
                entry = models.FactCompetitorPriceDaily(
                    date=date.fromisoformat(row["date"]),
                    sku_id=row["sku_id"],
                    competitor_name=row.get("competitor_name", "Unknown"),
                    price=float(row["price"]) if row.get("price") else None,
                    url=row.get("url"),
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "competitor_prices", db, current_user, _proc)


@router.post("/inventory")
async def upload_inventory(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        from datetime import date
        for row in rows:
            try:
                entry = models.FactInventoryDaily(
                    date=date.fromisoformat(row["date"]),
                    sku_id=row["sku_id"],
                    stock_quantity=int(row.get("stock_quantity", 0)),
                    days_of_stock=float(row["days_of_stock"]) if row.get("days_of_stock") else None,
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "inventory", db, current_user, _proc)


@router.post("/substitutions")
async def upload_substitutions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        for row in rows:
            try:
                entry = models.MapSubstitution(
                    a_brand_sku=row["a_brand_sku"],
                    private_label_sku=row["private_label_sku"],
                    substitution_strength=float(row.get("substitution_strength", 1.0)),
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "substitutions", db, current_user, _proc)


@router.post("/basket-affinity")
async def upload_basket_affinity(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        for row in rows:
            try:
                entry = models.FactBasketAffinity(
                    sku_id_a=row["sku_id_a"],
                    sku_id_b=row["sku_id_b"],
                    affinity_score=float(row.get("affinity_score", 0)),
                    co_purchase_count=int(row.get("co_purchase_count", 0)),
                )
                db.add(entry)
                processed += 1
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "basket_affinity", db, current_user, _proc)


@router.post("/price-rules")
async def upload_price_rules(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.require_role("admin", "pricing_manager")),
):
    def _proc(rows, db):
        processed, failed, warnings = 0, 0, []
        for row in rows:
            try:
                product = db.query(models.DimProduct).filter(
                    models.DimProduct.sku_id == row.get("sku_id")
                ).first()
                if product:
                    if row.get("min_price"):
                        product.min_price = float(row["min_price"])
                    if row.get("max_price"):
                        product.max_price = float(row["max_price"])
                    processed += 1
                else:
                    failed += 1
                    warnings.append(f"SKU {row.get('sku_id')} not found")
            except Exception as e:
                warnings.append(str(e))
                failed += 1
        db.commit()
        return processed, failed, warnings
    return await _process_upload(file, "price_rules", db, current_user, _proc)
