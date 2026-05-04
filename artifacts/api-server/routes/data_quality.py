"""Data quality report endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
import models
import auth as auth_utils

router = APIRouter(prefix="/api", tags=["data-quality"])


@router.get("/data-quality")
def get_data_quality(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    total_skus = db.query(models.DimProduct).count()
    issues = []
    summary = {}

    # Missing cost price
    missing_cost = db.query(models.DimProduct).filter(models.DimProduct.cost_price.is_(None)).count()
    if missing_cost:
        issues.append({"sku_id": None, "issue_type": "MISSING_COST_PRICE", "severity": "error",
                        "message": "SKUs missing cost price (required for margin calculation)", "affected_count": missing_cost})
        summary["MISSING_COST_PRICE"] = missing_cost

    # Missing min/max price
    missing_minmax = db.query(models.DimProduct).filter(
        models.DimProduct.min_price.is_(None) | models.DimProduct.max_price.is_(None)
    ).count()
    if missing_minmax:
        issues.append({"sku_id": None, "issue_type": "MISSING_PRICE_GUARDRAILS", "severity": "warning",
                        "message": "SKUs missing min or max price guardrails", "affected_count": missing_minmax})
        summary["MISSING_PRICE_GUARDRAILS"] = missing_minmax

    # Missing category
    missing_cat = db.query(models.DimProduct).filter(models.DimProduct.category.is_(None)).count()
    if missing_cat:
        issues.append({"sku_id": None, "issue_type": "MISSING_CATEGORY", "severity": "warning",
                        "message": "SKUs without category assignment", "affected_count": missing_cat})
        summary["MISSING_CATEGORY"] = missing_cat

    # Missing strategy type
    missing_strategy = db.query(models.DimProduct).filter(models.DimProduct.strategy_type.is_(None)).count()
    if missing_strategy:
        issues.append({"sku_id": None, "issue_type": "MISSING_STRATEGY_TYPE", "severity": "error",
                        "message": "SKUs without a pricing strategy type", "affected_count": missing_strategy})
        summary["MISSING_STRATEGY_TYPE"] = missing_strategy

    # Negative margins (price < cost)
    neg_margin_skus = db.query(models.DimProduct).filter(
        models.DimProduct.current_price.isnot(None),
        models.DimProduct.cost_price.isnot(None),
        models.DimProduct.current_price < models.DimProduct.cost_price,
    ).count()
    if neg_margin_skus:
        issues.append({"sku_id": None, "issue_type": "NEGATIVE_MARGIN", "severity": "error",
                        "message": "SKUs where current price is below cost price", "affected_count": neg_margin_skus})
        summary["NEGATIVE_MARGIN"] = neg_margin_skus

    # No competitor data
    skus_with_comp = db.query(models.FactCompetitorPriceDaily.sku_id).distinct().count()
    no_comp_data = total_skus - skus_with_comp
    if no_comp_data > 0:
        issues.append({"sku_id": None, "issue_type": "MISSING_COMPETITOR_DATA", "severity": "warning",
                        "message": "SKUs without any competitor price data", "affected_count": no_comp_data})
        summary["MISSING_COMPETITOR_DATA"] = no_comp_data

    # No stock data
    skus_with_stock = db.query(models.FactInventoryDaily.sku_id).distinct().count()
    no_stock_data = total_skus - skus_with_stock
    if no_stock_data > 0:
        issues.append({"sku_id": None, "issue_type": "MISSING_STOCK_DATA", "severity": "warning",
                        "message": "SKUs without inventory/stock data", "affected_count": no_stock_data})
        summary["MISSING_STOCK_DATA"] = no_stock_data

    # Min price > max price
    invalid_range = db.query(models.DimProduct).filter(
        models.DimProduct.min_price.isnot(None),
        models.DimProduct.max_price.isnot(None),
        models.DimProduct.min_price > models.DimProduct.max_price,
    ).count()
    if invalid_range:
        issues.append({"sku_id": None, "issue_type": "INVALID_PRICE_RANGE", "severity": "error",
                        "message": "SKUs where min_price > max_price", "affected_count": invalid_range})
        summary["INVALID_PRICE_RANGE"] = invalid_range

    # Compute overall score (100% = no issues, penalize by error severity)
    error_count = sum(1 for i in issues if i["severity"] == "error")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")
    score = max(0.0, 1.0 - (error_count * 0.15) - (warning_count * 0.05))

    return {
        "overall_score": round(score, 2),
        "total_skus": total_skus,
        "issues": issues,
        "summary": summary,
    }
