"""
Copilot met echte platformdata (taak #298):
- nieuwe semantic functions: get_assortment_overview en
  get_portfolio_price_position (registratie, permissies, tool-schema's)
- data-gedreven antwoorden: records > 0 met geseede data, data_available-vlag
- shop-scoping van de assortimentsfunctie
- budgetkalibratie: realistische upfront-reservering vs harde per-verzoek cap

Conventies: eigen DimShop met uuid-prefix; geen registry-syncs.
"""
import os
import sys
import types
import unittest
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DISABLE_SCRAPE_SCHEDULER", "true")

import ai_gateway  # noqa: E402
import models  # noqa: E402
import semantic_layer as sl  # noqa: E402

NEW_FUNCTIONS = ["get_assortment_overview", "get_portfolio_price_position"]


def _user(role="viewer"):
    u = types.SimpleNamespace()
    u.username = "test_user"
    u.role = role
    u.id = 999
    return u


class TestRegistration(unittest.TestCase):
    def test_registered_in_semantic_functions(self):
        for name in NEW_FUNCTIONS:
            self.assertIn(name, sl.SEMANTIC_FUNCTIONS)

    def test_tool_parameters_defined(self):
        for name in NEW_FUNCTIONS:
            self.assertIn(name, ai_gateway._TOOL_PARAMETERS)

    def test_permission_mapping(self):
        self.assertIsNone(ai_gateway.FUNCTION_PERMISSIONS["get_assortment_overview"])
        self.assertEqual(
            ai_gateway.FUNCTION_PERMISSIONS["get_portfolio_price_position"],
            "competition.view")

    def test_hierarchy_capable(self):
        for name in NEW_FUNCTIONS:
            self.assertIn(name, ai_gateway.HIERARCHY_CAPABLE_FUNCTIONS)

    def test_build_tools_includes_new_functions(self):
        names = {t["function"]["name"] for t in ai_gateway.build_tools()}
        for name in NEW_FUNCTIONS:
            self.assertIn(name, names)


class PortfolioDataBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from database import SessionLocal, engine
        models.Base.metadata.create_all(bind=engine)
        cls.db = SessionLocal()
        cls.pfx = f"PF-{uuid.uuid4().hex[:6]}"
        cls.shop = models.DimShop(shop_code=f"{cls.pfx}-A", name=f"{cls.pfx} Shop A")
        cls.shop_b = models.DimShop(shop_code=f"{cls.pfx}-B", name=f"{cls.pfx} Shop B")
        cls.db.add_all([cls.shop, cls.shop_b])
        cls.db.flush()
        skus = []
        for i in range(5):
            sku = f"{cls.pfx}-SKU-{i}"
            skus.append(sku)
            cls.db.add(models.DimProduct(
                sku_id=sku, product_name=f"{cls.pfx} product {i}",
                brand="MerkX" if i % 2 == 0 else "MerkY",
                category="CatA" if i < 3 else "CatB",
                lifecycle_status="active", current_price=10 + i,
                is_private_label=(i == 0), shop_id=cls.shop.id))
        # Concurrentprijzen op de laatste dag voor 3 van de 5 SKU's
        for sku in skus[:3]:
            cls.db.add(models.FactCompetitorPriceDaily(
                date=date(2026, 8, 24), sku_id=sku, shop_id=cls.shop.id,
                competitor_name="conc.nl", price=9.99))
        # Product in andere shop (scoping)
        cls.db.add(models.DimProduct(
            sku_id=f"{cls.pfx}-B-SKU", product_name=f"{cls.pfx} B-product",
            lifecycle_status="active", shop_id=cls.shop_b.id))
        # PCIS-scores: run van vandaag met prijsindex-spreiding
        run = date(2026, 8, 24)
        for i, (sku, pidx) in enumerate(zip(skus, [0.90, 0.95, 1.00, 1.05, None])):
            cls.db.add(models.SkuCompetitionScore(
                shop_id=cls.shop.id, sku_id=sku, run_date=run,
                pcis_score=0.5 + i * 0.05, price_index=pidx,
                competition_class="Monitor" if i < 3 else "Strong"))
        cls.db.commit()
        cls.skus = skus

    @classmethod
    def tearDownClass(cls):
        db = cls.db
        db.query(models.SkuCompetitionScore).filter(
            models.SkuCompetitionScore.sku_id.like(f"{cls.pfx}%")).delete(
            synchronize_session=False)
        db.query(models.FactCompetitorPriceDaily).filter(
            models.FactCompetitorPriceDaily.sku_id.like(f"{cls.pfx}%")).delete(
            synchronize_session=False)
        db.query(models.DimProduct).filter(
            models.DimProduct.sku_id.like(f"{cls.pfx}%")).delete(
            synchronize_session=False)
        db.query(models.CostUsageRecord).filter(
            models.CostUsageRecord.username == "test_user").delete(
            synchronize_session=False)
        for shop in (cls.shop, cls.shop_b):
            db.query(models.DimShop).filter(
                models.DimShop.id == shop.id).delete(synchronize_session=False)
        db.commit()
        db.close()


class TestAssortmentOverview(PortfolioDataBase):
    def test_records_and_counts(self):
        out = sl.get_assortment_overview(self.db, _user(), shop_id=self.shop.id)
        self.assertTrue(out["data_available"])
        self.assertEqual(out["records"], 5)
        self.assertEqual(out["total_products"], 5)
        self.assertEqual(out["active_products"], 5)
        self.assertEqual(out["distinct_brands"], 2)
        self.assertEqual(out["distinct_categories"], 2)
        self.assertEqual(out["private_label_products"], 1)
        self.assertEqual(out["products_with_own_price"], 5)

    def test_shop_scoped(self):
        out_b = sl.get_assortment_overview(self.db, _user(), shop_id=self.shop_b.id)
        self.assertEqual(out_b["total_products"], 1)
        self.assertNotIn(f"{self.pfx}-SKU-0",
                         [c["category"] for c in out_b["top_categories"]])

    def test_top_lists_present(self):
        out = sl.get_assortment_overview(self.db, _user(), shop_id=self.shop.id)
        cats = {c["category"]: c["products"] for c in out["top_categories"]}
        self.assertEqual(cats.get("CatA"), 3)
        brands = {b["brand"]: b["products"] for b in out["top_brands"]}
        self.assertEqual(brands.get("MerkX"), 3)


class TestPortfolioPricePosition(PortfolioDataBase):
    def test_summary_over_scored_skus(self):
        out = sl.get_portfolio_price_position(self.db, _user())
        self.assertTrue(out["data_available"])
        self.assertGreater(out["records"], 0)
        self.assertGreaterEqual(out["skus_scored"], out["skus_with_price_index"])
        self.assertIn("avg_price_index", out)
        self.assertIn("cheaper_share_pct", out)
        self.assertIn("by_competition_class", out)
        # richting-uitleg aanwezig (memory: <1.0 = goedkoper)
        self.assertIn("goedkoper", out["price_index_explanation"])

    def test_counts_partition(self):
        out = sl.get_portfolio_price_position(self.db, _user())
        self.assertEqual(
            out["cheaper_count"] + out["at_par_count"] + out["more_expensive_count"],
            out["skus_with_price_index"])


class TestBudgetCalibration(unittest.TestCase):
    def test_reservation_realistic(self):
        """Reservering moet korte vragen niet blokkeren: ruim onder de
        standaard-daglimiet en onder de harde per-verzoek cap."""
        self.assertLessEqual(ai_gateway._UPFRONT_TOKEN_RESERVATION,
                             ai_gateway._PER_REQUEST_TOKEN_CAP)
        self.assertLessEqual(
            ai_gateway._UPFRONT_TOKEN_RESERVATION * 4,
            ai_gateway.DEFAULT_MAX_TOKENS_PER_DAY,
            "Met de standaard-daglimiet moeten minstens 4 vragen passen")
        self.assertGreaterEqual(ai_gateway._UPFRONT_TOKEN_RESERVATION,
                                ai_gateway._MAX_COMPLETION_PER_CALL)

    def test_cap_covers_worst_case(self):
        self.assertGreaterEqual(
            ai_gateway._PER_REQUEST_TOKEN_CAP,
            ai_gateway.MAX_TOOL_ROUNDS * ai_gateway._MAX_COMPLETION_PER_CALL)


if __name__ == "__main__":
    unittest.main()
