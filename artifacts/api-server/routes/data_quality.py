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
):  # noqa: C901
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

    # ── DRS-specifieke kwaliteitschecks ──────────────────────────────────────
    drs_issues = []
    drs_summary: dict[str, int] = {}

    # DRS: Duplicate SKUs (multiple rows with same sku_id)
    # Not possible in dim_product (PK), but check import_jobs for recent DRS imports
    # with duplicate warnings — instead check for missing productcode (brand) fields
    missing_brand = db.query(models.DimProduct).filter(
        models.DimProduct.brand.is_(None)
    ).count()
    if missing_brand:
        drs_issues.append({
            "sku_id": None,
            "issue_type": "DRS_MISSING_BRAND",
            "severity": "warning",
            "message": "SKU's zonder merknaam (vereist voor DRS-kwaliteit)",
            "affected_count": missing_brand,
        })
        drs_summary["DRS_MISSING_BRAND"] = missing_brand

    missing_price = db.query(models.DimProduct).filter(
        models.DimProduct.current_price.is_(None)
    ).count()
    if missing_price:
        drs_issues.append({
            "sku_id": None,
            "issue_type": "DRS_MISSING_PRICE",
            "severity": "error",
            "message": "SKU's zonder verkoopprijs",
            "affected_count": missing_price,
        })
        drs_summary["DRS_MISSING_PRICE"] = missing_price

    # DRS: Missing hierarchy (products without a category matching dim_category_hierarchy)
    hier_count = db.query(models.DimCategoryHierarchy).filter(
        models.DimCategoryHierarchy.active == True
    ).count()
    if hier_count > 0:
        # Count products whose category has no match in the hierarchy
        hier_names = {
            row.category_name
            for row in db.query(models.DimCategoryHierarchy.category_name).all()
        }
        missing_hier = db.query(models.DimProduct).filter(
            models.DimProduct.category.notin_(hier_names)
        ).count() if hier_names else 0
        if missing_hier:
            drs_issues.append({
                "sku_id": None,
                "issue_type": "DRS_MISSING_HIERARCHY",
                "severity": "warning",
                "message": "SKU's waarvan de categorie niet in de DRS-hiërarchieboom staat",
                "affected_count": missing_hier,
            })
            drs_summary["DRS_MISSING_HIERARCHY"] = missing_hier

    # DRS: Inactive articles (is_active = False)
    inactief = db.query(models.DimProduct).filter(
        models.DimProduct.is_active == False
    ).count()
    if inactief:
        drs_issues.append({
            "sku_id": None,
            "issue_type": "DRS_INACTIEVE_ARTIKELEN",
            "severity": "info",
            "message": "Inactieve artikelen in de productcatalogus (uit DRS-import)",
            "affected_count": inactief,
        })
        drs_summary["DRS_INACTIEVE_ARTIKELEN"] = inactief

    # DRS: Negative margin from YTD data
    neg_marge_ytd = db.query(models.DimProduct).filter(
        models.DimProduct.marge_ytd.isnot(None),
        models.DimProduct.marge_ytd < 0,
    ).count()
    if neg_marge_ytd:
        drs_issues.append({
            "sku_id": None,
            "issue_type": "DRS_NEGATIEVE_MARGE_YTD",
            "severity": "error",
            "message": "SKU's met negatieve YTD-marge (DRS Datareport)",
            "affected_count": neg_marge_ytd,
        })
        drs_summary["DRS_NEGATIEVE_MARGE_YTD"] = neg_marge_ytd

    issues.extend(drs_issues)
    summary.update(drs_summary)

    # Compute overall score (100% = no issues, penalize by error severity)
    error_count = sum(1 for i in issues if i["severity"] == "error")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")
    score = max(0.0, 1.0 - (error_count * 0.15) - (warning_count * 0.05))

    return {
        "overall_score": round(score * 100, 1),
        "total_skus": total_skus,
        "issues": issues,
        "summary": summary,
        "drs_summary": drs_summary,
        "drs_issues": drs_issues,
        "hierarchy_node_count": hier_count if hier_count else 0,
    }
