"""
Concurrentprofiel via de Copilot (taak #249):
- semantic functions: output, leeg-data-gedrag, informatielagen, shop-scoping
- RBAC (rollen) + gateway-permissiemapping (fail-closed allowlist)
- Competition Data Quality-detecties (CP_*) in de bestaande scan-pipeline

Conventies: eigen DimShops met uuid-prefix; detector-tests roepen alleen de
detectie aan (géén _sync_issue_registry), zodat het gedeelde register nooit
door synthetische data wordt ge-auto-resolved.
"""
import os
import sys
import types
import unittest
import uuid
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DISABLE_SCRAPE_SCHEDULER", "true")

from fastapi import HTTPException  # noqa: E402

import ai_gateway  # noqa: E402
import models  # noqa: E402
import semantic_layer as sl  # noqa: E402
import routes.data_quality as dq_module  # noqa: E402

NEW_FUNCTIONS = [
    "get_competitor_business_profile", "get_competitor_company_size",
    "get_competitor_geographic_presence", "get_competitor_fulfilment_profile",
    "get_competitor_financial_health", "get_competitor_procurement_power",
    "get_competitor_market_roles", "get_competitor_corporate_structure",
    "get_competitor_evolution", "compare_competitor_profiles",
    "get_competitor_future_threats", "get_competitor_profile_quality",
]

ANALYST_ONLY = {"get_competitor_financial_health",
                "get_competitor_procurement_power",
                "get_competitor_future_threats"}


def _user(role="viewer"):
    u = types.SimpleNamespace()
    u.username = "test_user"
    u.role = role
    u.id = 999
    return u


class CompetitorProfileBase(unittest.TestCase):
    """Gedeelde seed: shop A met concurrenten in verschillende kwaliteit,
    shop B met één concurrent (scoping)."""

    @classmethod
    def setUpClass(cls):
        from database import SessionLocal, engine
        models.Base.metadata.create_all(bind=engine)
        cls.db = SessionLocal()
        cls.pfx = f"CPT-{uuid.uuid4().hex[:6]}"
        shop_a = models.DimShop(shop_code=f"{cls.pfx}-a", name=f"{cls.pfx} A")
        shop_b = models.DimShop(shop_code=f"{cls.pfx}-b", name=f"{cls.pfx} B")
        cls.db.add_all([shop_a, shop_b])
        cls.db.flush()
        cls.sid_a, cls.sid_b = shop_a.id, shop_b.id

        cls.bad = f"{cls.pfx}-Slecht BV"       # veel kwaliteitsissues
        cls.good = f"{cls.pfx}-Goed GmbH"      # compleet profiel, dropship
        cls.sister = f"{cls.pfx}-Zus BV"       # zelfde groep als good
        cls.own = f"{cls.pfx}-Voorraad BV"     # eigen voorraad (geen dropship)
        cls.b_only = f"{cls.pfx}-AndereShop"   # alleen in shop B

        now = datetime.utcnow()
        old = (now - timedelta(days=800)).isoformat()
        fresh_meta = {"information_layer": "feit", "confidence": 0.9,
                      "source": "jaarverslag", "last_verified_at": now.isoformat()}

        db = cls.db
        for name in (cls.bad, cls.good, cls.sister, cls.own):
            db.add(models.CompetitorProfile(
                shop_id=cls.sid_a, competitor_name=name,
                relevance_label="HIGH" if name != cls.sister else "LOW"))
        db.add(models.CompetitorProfile(shop_id=cls.sid_b,
                                        competitor_name=cls.b_only))

        # 'bad': size/founded/ownership onbekend, stale employees, lage conf
        db.add(models.CompetitorBusinessProfile(
            shop_id=cls.sid_a, competitor_name=cls.bad,
            employee_range_min=10, employee_range_max=50,
            field_meta={"employee_range_min": {
                "information_layer": "schatting", "confidence": 0.3,
                "last_verified_at": old}}))
        # conflicterende financiën (zelfde metric/boekjaar, geen overlap, geen bron)
        db.add(models.CompetitorFinancialObservation(
            shop_id=cls.sid_a, competitor_name=cls.bad, fiscal_year=2024,
            metric="revenue", value_min=1_000_000, value_max=2_000_000,
            confidence=0.3, last_verified_at=now))
        db.add(models.CompetitorFinancialObservation(
            shop_id=cls.sid_a, competitor_name=cls.bad, fiscal_year=2024,
            metric="revenue", value_min=10_000_000, value_max=20_000_000,
            confidence=0.4, last_verified_at=now))

        # 'good': volledig profiel, groot/internationaal, dropship-speler
        db.add(models.CompetitorBusinessProfile(
            shop_id=cls.sid_a, competitor_name=cls.good,
            size_class="groot", founded_year=1992,
            employee_range_min=500, employee_range_max=1000,
            revenue_range_min=50_000_000, revenue_range_max=80_000_000,
            revenue_currency="EUR", geographic_scale="internationaal",
            ownership_type="private_equity",
            field_meta={f: dict(fresh_meta) for f in (
                "size_class", "founded_year", "employee_range_min",
                "employee_range_max", "revenue_range_min", "revenue_range_max",
                "geographic_scale", "ownership_type")}))
        db.add(models.CompetitorFulfilmentProfile(
            shop_id=cls.sid_a, competitor_name=cls.good,
            inventory_model="dropship", dropship_share_pct=85.0,
            field_meta={"inventory_model": dict(fresh_meta),
                        "dropship_share_pct": dict(fresh_meta)}))
        db.add(models.CompetitorFulfilmentProfile(
            shop_id=cls.sid_a, competitor_name=cls.own,
            inventory_model="eigen_voorraad", own_stock_share_pct=100.0,
            field_meta={"inventory_model": dict(fresh_meta)}))
        db.add(models.CompetitorGeographicPresence(
            shop_id=cls.sid_a, competitor_name=cls.good,
            country_code="DE", presence_type="webshop", confidence=0.9,
            last_verified_at=now))
        db.add(models.CompetitorFinancialObservation(
            shop_id=cls.sid_a, competitor_name=cls.good, fiscal_year=2025,
            metric="revenue", value_min=60_000_000, value_max=70_000_000,
            information_layer="feit", confidence=0.9,
            source_note="jaarrekening", last_verified_at=now))
        db.add(models.CompetitorMarketRole(
            shop_id=cls.sid_a, competitor_name=cls.good, role="prijsvechter",
            confidence=0.8, last_verified_at=now))
        # zelfde groep: good + sister onder dezelfde ultimate parent
        for name in (cls.good, cls.sister):
            db.add(models.CompetitorCorporateRelation(
                shop_id=cls.sid_a, competitor_name=name,
                relation_type="ultimate_parent",
                related_entity=f"{cls.pfx}-Group Holding", confidence=0.9))
        # heronderzoek-verzoek op sister
        db.add(models.CompetitorFieldValidation(
            shop_id=cls.sid_a, competitor_name=cls.sister,
            section="business", field_name="size_class",
            action="heronderzoek", reviewer="tester", is_current=True))
        # evolution-event op good
        db.add(models.CompetitorEvolutionEvent(
            shop_id=cls.sid_a, competitor_name=cls.good, section="fulfilment",
            field_name="dropship_share_pct", event_type="changed",
            old_value=70, new_value=85, change_source="handmatig",
            occurred_at=now))
        # scores: good bekend, bad expliciet unknown (NULL)
        db.add(models.CompetitorScoreResult(
            shop_id=cls.sid_a, competitor_name=cls.good, run_date=date.today(),
            company_size_class="groot", geographic_scale_class="internationaal",
            fulfilment_model_class="dropship",
            financial_health_score=82.0, financial_health_status="gezond",
            procurement_power_score=77.0, future_threat_score=64.0,
            data_completeness_pct=90.0))
        db.add(models.CompetitorScoreResult(
            shop_id=cls.sid_a, competitor_name=cls.bad, run_date=date.today(),
            data_completeness_pct=10.0))
        # shop B: eigen profiel, mag nooit in shop A-antwoorden lekken
        db.add(models.CompetitorBusinessProfile(
            shop_id=cls.sid_b, competitor_name=cls.b_only, size_class="groot",
            geographic_scale="internationaal"))
        db.commit()

    @classmethod
    def tearDownClass(cls):
        db = cls.db
        for model in (models.CompetitorBusinessProfile,
                      models.CompetitorFulfilmentProfile,
                      models.CompetitorFinancialObservation,
                      models.CompetitorMarketRole,
                      models.CompetitorGeographicPresence,
                      models.CompetitorCorporateRelation,
                      models.CompetitorEvolutionEvent,
                      models.CompetitorFieldValidation,
                      models.CompetitorScoreResult,
                      models.CompetitorProfile):
            db.query(model).filter(
                model.competitor_name.like(f"{cls.pfx}%")).delete(
                synchronize_session=False)
        db.query(models.DimShop).filter(
            models.DimShop.id.in_([cls.sid_a, cls.sid_b])).delete(
            synchronize_session=False)
        db.commit()
        db.close()


class TestSemanticFunctions(CompetitorProfileBase):

    def test_business_profile_fields_with_layers(self):
        res = sl.get_competitor_business_profile(
            self.db, _user("viewer"), competitor_name=self.good,
            shop_id=self.sid_a)
        self.assertTrue(res["data_available"])
        self.assertIn("information_layer_note", res)
        f = res["fields"]["size_class"]
        self.assertEqual(f["value"], "groot")
        self.assertEqual(f["information_layer"], "feit")
        self.assertEqual(f["source"], "jaarverslag")

    def test_business_profile_empty_data_safe(self):
        res = sl.get_competitor_business_profile(
            self.db, _user("viewer"), competitor_name="Bestaat Niet BV",
            shop_id=self.sid_a)
        self.assertFalse(res["data_available"])

    def test_company_size_filter_large_international(self):
        res = sl.get_competitor_company_size(
            self.db, _user("viewer"), size_class="groot",
            geographic_scale="internationaal", shop_id=self.sid_a)
        names = {i["competitor_name"] for i in res["items"]}
        self.assertIn(self.good, names)
        self.assertNotIn(self.bad, names)
        self.assertNotIn(self.b_only, names)  # shop-scoping

    def test_fulfilment_dropship_only(self):
        res = sl.get_competitor_fulfilment_profile(
            self.db, _user("viewer"), dropship_only=True, shop_id=self.sid_a)
        names = {i["competitor_name"] for i in res["items"]}
        self.assertIn(self.good, names)
        self.assertNotIn(self.own, names)

    def test_financial_health_includes_relevance_and_layers(self):
        res = sl.get_competitor_financial_health(
            self.db, _user("analyst"), shop_id=self.sid_a)
        by_name = {i["competitor_name"]: i for i in res["items"]}
        good = by_name[self.good]
        self.assertEqual(good["financial_health_status"], "gezond")
        self.assertEqual(good["relevance_label"], "HIGH")
        self.assertEqual(good["observations"][0]["information_layer"], "feit")
        # NULL-score = unknown, nooit 0
        self.assertIsNone(by_name[self.bad]["financial_health_score"])
        self.assertEqual(by_name[self.bad]["financial_health_status"], "unknown")

    def test_procurement_power_ranking_unknown_last(self):
        res = sl.get_competitor_procurement_power(
            self.db, _user("analyst"), limit=100, shop_id=self.sid_a)
        items = [i for i in res["items"]
                 if i["competitor_name"].startswith(self.pfx)]
        self.assertEqual(items[0]["competitor_name"], self.good)
        unknown = [i for i in items if i["competitor_name"] == self.bad][0]
        self.assertTrue(unknown["score_is_unknown"])
        self.assertIsNone(unknown["procurement_power_score"])

    def test_corporate_structure_same_group(self):
        res = sl.get_competitor_corporate_structure(
            self.db, _user("viewer"), shop_id=self.sid_a)
        groups = {g["group_parent"]: g["competitors"]
                  for g in res["shared_groups"]}
        self.assertIn(f"{self.pfx}-Group Holding", groups)
        self.assertEqual(sorted(groups[f"{self.pfx}-Group Holding"]),
                         sorted([self.good, self.sister]))

    def test_market_roles_and_geography(self):
        roles = sl.get_competitor_market_roles(
            self.db, _user("viewer"), role="prijsvechter", shop_id=self.sid_a)
        self.assertIn(self.good,
                      {i["competitor_name"] for i in roles["items"]})
        geo = sl.get_competitor_geographic_presence(
            self.db, _user("viewer"), country_code="de", shop_id=self.sid_a)
        self.assertIn(self.good, {i["competitor_name"] for i in geo["items"]})

    def test_evolution_timeline(self):
        res = sl.get_competitor_evolution(
            self.db, _user("viewer"), competitor_name=self.good,
            shop_id=self.sid_a)
        self.assertTrue(res["data_available"])
        self.assertEqual(res["events"][0]["field_name"], "dropship_share_pct")

    def test_compare_profiles(self):
        res = sl.compare_competitor_profiles(
            self.db, _user("viewer"),
            competitor_names=[self.good, self.bad], shop_id=self.sid_a)
        self.assertTrue(res["data_available"])
        self.assertEqual(len(res["items"]), 2)
        # te weinig namen = nette fout, geen crash
        err = sl.compare_competitor_profiles(
            self.db, _user("viewer"), competitor_names=[self.good],
            shop_id=self.sid_a)
        self.assertFalse(err["data_available"])
        self.assertIn("error", err)

    def test_future_threats_marked_as_derived_signal(self):
        res = sl.get_competitor_future_threats(
            self.db, _user("analyst"), limit=100, shop_id=self.sid_a)
        self.assertEqual(res["information_layer"], "afgeleid_signaal")
        items = [i for i in res["items"]
                 if i["competitor_name"].startswith(self.pfx)]
        self.assertEqual(items[0]["competitor_name"], self.good)

    def test_profile_quality_and_needs_recheck(self):
        res = sl.get_competitor_profile_quality(
            self.db, _user("viewer"), shop_id=self.sid_a, limit=100)
        by_name = {i["competitor_name"]: i for i in res["items"]}
        bad = by_name[self.bad]
        self.assertTrue(bad["needs_recheck"])
        self.assertEqual(bad["reliability"], "laag")
        for code in ("CP_UNKNOWN_COMPANY_SIZE", "CP_MISSING_FOUNDED_YEAR",
                     "CP_STALE_EMPLOYEE_ESTIMATE", "CP_UNKNOWN_FULFILMENT_MODEL",
                     "CP_UNKNOWN_DROPSHIP_MODEL", "CP_UNKNOWN_ACTIVE_COUNTRIES",
                     "CP_MISSING_OWNERSHIP", "CP_CONFLICTING_FINANCIALS",
                     "CP_MISSING_PROFILE_SOURCE", "CP_LOW_CONFIDENCE_PROFILE"):
            self.assertIn(code, bad["quality_flags"], code)
        # heronderzoek-verzoek telt mee
        self.assertTrue(by_name[self.sister]["needs_recheck"])
        self.assertEqual(by_name[self.sister]["open_recheck_requests"], 1)
        self.assertFalse(by_name[self.good]["needs_recheck"])
        # needs_recheck_only filtert
        only = sl.get_competitor_profile_quality(
            self.db, _user("viewer"), needs_recheck_only=True,
            shop_id=self.sid_a, limit=100)
        names = {i["competitor_name"] for i in only["items"]}
        self.assertIn(self.bad, names)
        self.assertNotIn(self.good, names)


class TestRbacAndGateway(CompetitorProfileBase):

    def test_viewer_denied_on_analyst_functions(self):
        for name in ANALYST_ONLY:
            fn = sl.SEMANTIC_FUNCTIONS[name].fn
            with self.assertRaises(HTTPException) as ctx:
                fn(self.db, _user("viewer"), shop_id=self.sid_a)
            self.assertEqual(ctx.exception.status_code, 403)

    def test_analyst_allowed_on_analyst_functions(self):
        for name in ANALYST_ONLY:
            res = sl.SEMANTIC_FUNCTIONS[name].fn(
                self.db, _user("analyst"), shop_id=self.sid_a)
            self.assertIn("data_available", res)

    def test_all_new_functions_registered_and_permission_mapped(self):
        for name in NEW_FUNCTIONS:
            self.assertIn(name, sl.SEMANTIC_FUNCTIONS, name)
            # fail-closed: expliciete permissie, nooit None (=onbeperkt)
            self.assertEqual(ai_gateway.FUNCTION_PERMISSIONS.get(name),
                             "competition.view", name)
            self.assertIn(name, ai_gateway._TOOL_PARAMETERS, name)

    def test_tools_filtered_by_allowlist(self):
        tools = ai_gateway.build_tools({"get_product_performance"})
        names = {t["function"]["name"] for t in tools}
        self.assertEqual(names, {"get_product_performance"})

    def test_execute_tool_denies_without_department_permission(self):
        result, meta = ai_gateway._execute_tool(
            self.db, _user("admin"), "get_competitor_profile_quality", {},
            shop_id=self.sid_a, allowed_functions=set())
        self.assertEqual(meta.get("denied"), "department_permission")
        self.assertFalse(result["data_available"])
        self.assertIn("competition.view", result["error"])

    def test_injected_shop_id_dropped(self):
        result, meta = ai_gateway._execute_tool(
            self.db, _user("admin"), "get_competitor_company_size",
            {"shop_id": self.sid_b, "bogus": 1, "limit": 100},
            shop_id=self.sid_a,
            allowed_functions={"get_competitor_company_size"})
        self.assertIn("shop_id", meta.get("dropped_arguments", []))
        self.assertIn("bogus", meta.get("dropped_arguments", []))
        self.assertEqual(result.get("shop_id"), self.sid_a)
        names = {i["competitor_name"] for i in result.get("items", [])}
        self.assertNotIn(self.b_only, names)


class TestCompetitorDataQualityScan(CompetitorProfileBase):
    """Detector-only: geen _sync_issue_registry-aanroep met testdata, zodat
    het gedeelde issue-register onaangeroerd blijft (registry-isolatie)."""

    def test_cp_detections_present(self):
        issues = dq_module._detect_competitor_profile_issues(self.db)
        by_code = {i["issue_code"]: i for i in issues}
        for code in ("CP_UNKNOWN_COMPANY_SIZE", "CP_MISSING_FOUNDED_YEAR",
                     "CP_STALE_EMPLOYEE_ESTIMATE", "CP_UNKNOWN_FULFILMENT_MODEL",
                     "CP_UNKNOWN_DROPSHIP_MODEL", "CP_UNKNOWN_ACTIVE_COUNTRIES",
                     "CP_MISSING_OWNERSHIP", "CP_CONFLICTING_FINANCIALS",
                     "CP_MISSING_PROFILE_SOURCE", "CP_LOW_CONFIDENCE_PROFILE"):
            self.assertIn(code, by_code, code)
            self.assertGreaterEqual(by_code[code]["affected_count"], 1)
            self.assertEqual(by_code[code]["module"], "Concurrentprofielen")
            self.assertEqual(by_code[code]["source"], "Competition")
        self.assertEqual(by_code["CP_CONFLICTING_FINANCIALS"]["severity"], "error")

    def test_inconsistent_parent_detection(self):
        # tijdelijk: twee verschillende actieve parents voor dezelfde concurrent
        rows = [models.CompetitorCorporateRelation(
                    shop_id=self.sid_a, competitor_name=self.own,
                    relation_type="parent", related_entity=f"{self.pfx}-P{i}")
                for i in (1, 2)]
        self.db.add_all(rows)
        self.db.commit()
        try:
            issues = dq_module._detect_competitor_profile_issues(self.db)
            codes = {i["issue_code"] for i in issues}
            self.assertIn("CP_INCONSISTENT_PARENT_RELATIONS", codes)
        finally:
            for r in rows:
                self.db.delete(r)
            self.db.commit()

    def test_detections_flow_through_main_detector(self):
        """CP_*-detecties komen mee via de bestaande _detect_issues-pipeline
        (geen tweede entry point)."""
        issues = dq_module._detect_issues(self.db, total_skus=0)
        codes = {i["issue_code"] for i in issues}
        self.assertIn("CP_UNKNOWN_COMPANY_SIZE", codes)


if __name__ == "__main__":
    unittest.main()
