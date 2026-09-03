"""
AI Gateway-garanties (§31/§32/§56):
- PII-filter: geen persoonsgegevens richting het externe model
- Tool-autorisatie: rollen en gesloten functielijst
- Shop-scoping van de nieuwe Copilot-functies
- Fail-safe zonder geconfigureerde provider
"""
import os
import sys
import types
import unittest
import unittest.mock
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DISABLE_SCRAPE_SCHEDULER", "true")

import ai_gateway  # noqa: E402
from semantic_layer import SEMANTIC_FUNCTIONS, get_competitor_ranking  # noqa: E402


def _user(role="viewer"):
    u = types.SimpleNamespace()
    u.username = "test_user"
    u.role = role
    u.id = 999
    return u


class TestPiiScrub(unittest.TestCase):
    def test_pii_keys_removed(self):
        data = {"email": "a@b.nl", "full_name": "Jan Jansen", "phone": "0612345678",
                "address": "Straat 1", "hashed_password": "x", "revenue": 12.5}
        out = ai_gateway.pii_scrub(data)
        self.assertEqual(out, {"revenue": 12.5})

    def test_pseudonymous_id_preserved(self):
        out = ai_gateway.pii_scrub({"pseudonymous_customer_id": "PSX1", "email": "a@b.nl"})
        self.assertEqual(out, {"pseudonymous_customer_id": "PSX1"})

    def test_patterns_masked_in_strings(self):
        s = ai_gateway.pii_scrub("mail jan.jansen@example.com of bel 06-12345678")
        self.assertNotIn("@example.com", s)
        self.assertNotIn("12345678", s)
        self.assertIn("[e-mail verwijderd]", s)
        self.assertIn("[telefoonnummer verwijderd]", s)

    def test_iso_datetimes_not_masked_as_phone(self):
        # Regressie: PII-scrubber verminkte timestamps in data_freshness
        # ("2[telefoonnummer verwijderd]:59:17.901630").
        for ts in (
            "2026-08-19 02:59:17.901630",
            "2026-08-19T02:59:17.901630",
            "laatste sync: 2026-08-19 02:59:17",
            "signals: 2025-12-01 00:08:09.123456",
            "2026-08-19",
        ):
            s = ai_gateway.pii_scrub(ts)
            self.assertEqual(s, ts, ts)
            self.assertNotIn("[telefoonnummer verwijderd]", s)

    def test_real_phone_numbers_still_masked(self):
        for txt in (
            "bel 0612345678",
            "bel 06-12345678",
            "bel 06 12 34 56 78",
            "bel +31612345678",
            "bel 0031612345678",
            "vast nummer 010-1234567",
        ):
            s = ai_gateway.pii_scrub(txt)
            self.assertIn("[telefoonnummer verwijderd]", s, txt)

    def test_iban_masked(self):
        s = ai_gateway.pii_scrub("mijn rekening is NL91ABNA0417164300 graag")
        self.assertNotIn("NL91ABNA0417164300", s)
        self.assertIn("[IBAN verwijderd]", s)

    def test_bsn_masked_with_elfproef(self):
        s = ai_gateway.pii_scrub("mijn bsn is 111222333")  # geldige elfproef
        self.assertNotIn("111222333", s)
        self.assertIn("[BSN verwijderd]", s)
        # een 9-cijferig getal dat GEEN geldig BSN is blijft staan (geen PII)
        s2 = ai_gateway.pii_scrub("ordernummer 123456789")
        self.assertIn("123456789", s2)

    def test_address_and_postcode_masked(self):
        s = ai_gateway.pii_scrub("bezorg op Hoofdstraat 12a, 1234 AB Amsterdam")
        self.assertNotIn("Hoofdstraat 12", s)
        self.assertNotIn("1234 AB", s)
        self.assertIn("[adres verwijderd]", s)
        self.assertIn("[postcode verwijderd]", s)

    def test_names_masked(self):
        for txt, leak in (
            ("mijn naam is Jan Jansen en ik wil marges zien", "Jan Jansen"),
            ("de heer Pieter van den Berg vroeg om korting", "Pieter van den Berg"),
            ("contactpersoon: Sanne de Vries", "Sanne de Vries"),
            ("ik heet Ahmed El Idrissi", "Ahmed El Idrissi"),
        ):
            s = ai_gateway.pii_scrub(txt)
            self.assertNotIn(leak, s, txt)
            self.assertIn("[naam verwijderd]", s)

    def test_pii_in_tool_result_text_masked(self):
        # PII die in tool-resultaatteksten zou zitten (bv. genoteerd in een
        # vrije-tekstveld) wordt óók gemaskeerd.
        data = {"items": [{"note": "bel dhr. Jansen op 0612345678, IBAN NL91ABNA0417164300"}]}
        out = ai_gateway.pii_scrub(data)
        note = out["items"][0]["note"]
        for leak in ("Jansen", "0612345678", "NL91ABNA0417164300"):
            self.assertNotIn(leak, note)

    def test_nested_structures(self):
        data = {"items": [{"email": "a@b.nl", "note": "x@y.nl", "score": 1}]}
        out = ai_gateway.pii_scrub(data)
        self.assertEqual(out["items"][0]["score"], 1)
        self.assertNotIn("email", out["items"][0])
        self.assertNotIn("@", out["items"][0]["note"])


class TestToolAuthorization(unittest.TestCase):
    def test_unknown_function_rejected(self):
        result, meta = ai_gateway._execute_tool(None, _user("admin"), "run_free_sql", {})
        self.assertIn("niet goedgekeurd", result["error"])

    def test_viewer_denied_analyst_tools(self):
        for name in ("get_supplier_risk", "simulate_price_change"):
            sem = SEMANTIC_FUNCTIONS[name]
            self.assertNotIn("viewer", sem.required_roles)
            result, _ = ai_gateway._execute_tool(
                None, _user("viewer"), name,
                {"sku_id": "X", "change_pct": 0.03} if name == "simulate_price_change" else {})
            self.assertIn("error", result)
            self.assertEqual(result.get("status_code"), 403)

    def test_all_tools_are_approved_semantic_functions(self):
        tool_names = {t["function"]["name"] for t in ai_gateway.build_tools()}
        self.assertEqual(tool_names, set(SEMANTIC_FUNCTIONS.keys()))


class TestQuestionAndHistoryScrubbed(unittest.TestCase):
    def test_messages_to_provider_are_scrubbed(self):
        """De vraag en geschiedenis richting het model bevatten geen PII."""
        captured = {}

        class FakeMsg:
            tool_calls = None
            # het model echoot PII terug — het eindantwoord moet ook gescrubd worden
            content = '{"conclusion": "Neem contact op met dhr. Jansen via jan@x.nl", "confidence": 0.5}'

        class FakeResp:
            usage = None
            choices = [types.SimpleNamespace(message=FakeMsg())]

        class FakeCompletions:
            def create(self, **kwargs):
                captured["messages"] = kwargs["messages"]
                return FakeResp()

        class FakeClient:
            chat = types.SimpleNamespace(completions=FakeCompletions())

        class FakeDb:
            def query(self, *a, **k):
                raise RuntimeError("no db in test")
            def add(self, *a): pass
            def commit(self): pass
            def rollback(self): pass

        with patch.object(ai_gateway, "_make_client", return_value=(FakeClient(), "test")), \
             patch.object(ai_gateway, "get_data_freshness", return_value={}), \
             patch.object(ai_gateway, "_log_call", return_value=None):
            events = list(ai_gateway.run_copilot(
                FakeDb(), _user("admin"),
                history=[{"role": "user",
                          "content": "mijn mail is jan@x.nl, ik heet Jan Jansen, IBAN NL91ABNA0417164300"}],
                question="bel me op 06-12345678, bsn 111222333, adres Hoofdstraat 12, 1234 AB",
            ))
        blob = str(captured["messages"])
        for leak in ("jan@x.nl", "12345678", "Jan Jansen", "NL91ABNA0417164300",
                     "111222333", "Hoofdstraat 12", "1234 AB"):
            self.assertNotIn(leak, blob)
        answers = [e["answer"] for e in events if e["type"] == "answer"]
        self.assertEqual(len(answers), 1)
        # geëchode PII in het eindantwoord (dat ook gepersisteerd wordt) is gescrubd
        self.assertNotIn("jan@x.nl", answers[0]["conclusion"])
        self.assertNotIn("Jansen", answers[0]["conclusion"])


class TestFailSafe(unittest.TestCase):
    def test_no_provider_yields_structured_answer(self):
        class FakeDb:
            def add(self, *a): pass
            def commit(self): pass
            def rollback(self): pass

        with patch.object(ai_gateway, "_provider_config", return_value=None), \
             patch.object(ai_gateway, "get_data_freshness", return_value={}), \
             patch.object(ai_gateway, "_log_call", return_value=None):
            events = list(ai_gateway.run_copilot(FakeDb(), _user("viewer"), [], "test?"))
        answers = [e for e in events if e["type"] == "answer"]
        self.assertEqual(len(answers), 1)
        a = answers[0]["answer"]
        self.assertIn("niet geconfigureerd", a["conclusion"])
        self.assertEqual(a["confidence"], 0.0)
        self.assertTrue(a["warnings"])


class TestCompetitorRankingRecords(unittest.TestCase):
    @patch("semantic_layer._shop_scope", return_value=1)
    def test_filled_ranking_reports_competitor_count(self, _shop_scope):
        latest_query = unittest.mock.MagicMock()
        latest_query.join.return_value.filter.return_value.scalar.return_value = "2026-09-03"
        ranking_query = unittest.mock.MagicMock()
        ranking_query.join.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [
            types.SimpleNamespace(
                competitor_name="Concurrent A", avg_cis=80, avg_csrs=90, sku_count=4),
            types.SimpleNamespace(
                competitor_name="Concurrent B", avg_cis=70, avg_csrs=85, sku_count=3),
        ]
        db = unittest.mock.MagicMock()
        db.query.side_effect = [latest_query, ranking_query]

        result = get_competitor_ranking(db, _user(), shop_id=1)

        self.assertEqual(result["records"], 2)
        self.assertEqual(len(result["competitors"]), 2)
        self.assertTrue(result["data_available"])

    @patch("semantic_layer._shop_scope", return_value=1)
    def test_empty_ranking_reports_zero_records(self, _shop_scope):
        latest_query = unittest.mock.MagicMock()
        latest_query.join.return_value.filter.return_value.scalar.return_value = None
        db = unittest.mock.MagicMock()
        db.query.return_value = latest_query

        result = get_competitor_ranking(db, _user(), shop_id=1)

        self.assertEqual(result["records"], 0)
        self.assertEqual(result["competitors"], [])
        self.assertFalse(result["data_available"])



class TestCrossShopScoping(unittest.TestCase):
    """Copilot-functies zonder shop_id op de facttabel scopen via de SKU's
    van de shop (DimProduct) — data van een andere shop mag nooit lekken."""

    @classmethod
    def setUpClass(cls):
        import uuid
        from datetime import date
        from database import SessionLocal, engine
        import models
        # Zorg dat de tests ook geïsoleerd draaien: maak ontbrekende tabellen aan.
        models.Base.metadata.create_all(bind=engine)
        cls.db = SessionLocal()
        cls.pfx = f"AIGW-{uuid.uuid4().hex[:6]}"
        shop_a = models.DimShop(shop_code=f"{cls.pfx}-a", name=f"{cls.pfx} Shop A")
        shop_b = models.DimShop(shop_code=f"{cls.pfx}-b", name=f"{cls.pfx} Shop B")
        cls.db.add(shop_a)
        cls.db.add(shop_b)
        cls.db.flush()
        cls.sid_a = shop_a.id
        cls.sid_b = shop_b.id
        cls.sku_b = f"{cls.pfx}-SKU-B"
        cls.db.add(models.DimProduct(sku_id=cls.sku_b, product_name=f"{cls.pfx} B",
                                     shop_id=cls.sid_b))
        cls.db.add(models.FactPrivateLabelIntelligence(
            sku_id=cls.sku_b, run_date=date.today(),
            private_label_value_score=99.9))
        cls.db.add(models.FactProcurementForecastDaily(
            sku_id=cls.sku_b, date=date.today(),
            future_margin_risk_score=99.9))
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        import models
        for model, col in ((models.FactPrivateLabelIntelligence, models.FactPrivateLabelIntelligence.sku_id),
                           (models.FactProcurementForecastDaily, models.FactProcurementForecastDaily.sku_id),
                           (models.DimProduct, models.DimProduct.sku_id)):
            cls.db.query(model).filter(col == cls.sku_b).delete()
        cls.db.query(__import__("models").DimShop).filter(
            __import__("models").DimShop.id.in_([cls.sid_a, cls.sid_b])).delete()
        cls.db.commit()
        cls.db.close()

    def test_shop_a_does_not_see_shop_b_rows(self):
        from semantic_layer import get_private_label_potential, get_supplier_risk
        u = _user("admin")
        for fn in (get_private_label_potential, get_supplier_risk):
            res = fn(self.db, u, limit=500, shop_id=self.sid_a)
            self.assertTrue(res["shop_scope_applied"])
            skus = {i["sku_id"] for i in res.get("items", [])}
            self.assertNotIn(self.sku_b, skus)

    def test_injected_shop_id_cannot_alter_scope(self):
        """Prompt-injection: een door het model meegegeven shop_id wordt
        verworpen; de server-side scope (shop A) blijft gelden."""
        result, meta = ai_gateway._execute_tool(
            self.db, _user("admin"), "get_supplier_risk",
            {"shop_id": self.sid_b, "limit": 500, "bogus_arg": 1},
            shop_id=self.sid_a)
        self.assertIn("shop_id", meta.get("dropped_arguments", []))
        self.assertIn("bogus_arg", meta.get("dropped_arguments", []))
        self.assertEqual(result.get("shop_id"), self.sid_a)
        skus = {i["sku_id"] for i in result.get("items", [])}
        self.assertNotIn(self.sku_b, skus)

    def test_shop_b_sees_own_rows(self):
        from semantic_layer import get_private_label_potential, get_supplier_risk
        u = _user("admin")
        for fn in (get_private_label_potential, get_supplier_risk):
            res = fn(self.db, u, limit=500, shop_id=self.sid_b)
            skus = {i["sku_id"] for i in res.get("items", [])}
            self.assertIn(self.sku_b, skus)


class TestProbe(unittest.TestCase):
    """_run_probe: 404/405 op GET /models is alleen voor de Replit-gateway
    acceptabel, en dan pas na een geslaagde minimale chat-completion."""

    def _exc(self, status):
        exc = Exception(f"Error code: {status}")
        exc.status_code = status
        return exc

    def _fake_client(self, models_exc, chat_ok=True, chat_exc=None):
        client = types.SimpleNamespace()
        client.models = types.SimpleNamespace(
            list=unittest.mock.Mock(side_effect=models_exc))
        create = unittest.mock.Mock()
        if not chat_ok:
            create.side_effect = chat_exc or Exception("chat kapot")
        client.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create))
        return client

    def _probe_with(self, provider, client):
        cfg = {"base_url": "https://example", "api_key": "x", "provider": provider}
        fake_openai = types.SimpleNamespace(OpenAI=lambda **kw: client)
        with patch.object(ai_gateway, "_env_config", return_value=cfg), \
             patch.dict(sys.modules, {"openai": fake_openai}):
            return ai_gateway._run_probe(provider)

    def test_replit_405_with_working_chat_is_reachable(self):
        client = self._fake_client(self._exc(405), chat_ok=True)
        ok, err = self._probe_with(ai_gateway.PROVIDER_REPLIT, client)
        self.assertTrue(ok)
        self.assertIsNone(err)
        client.chat.completions.create.assert_called_once()

    def test_replit_405_with_broken_chat_is_unreachable(self):
        client = self._fake_client(self._exc(405), chat_ok=False,
                                   chat_exc=self._exc(401))
        ok, err = self._probe_with(ai_gateway.PROVIDER_REPLIT, client)
        self.assertFalse(ok)
        self.assertIn("401", err)

    def test_direct_405_stays_unreachable(self):
        client = self._fake_client(self._exc(405), chat_ok=True)
        ok, err = self._probe_with(ai_gateway.PROVIDER_OPENAI, client)
        self.assertFalse(ok)
        self.assertIn("405", err)
        client.chat.completions.create.assert_not_called()

    def test_auth_error_stays_unreachable(self):
        client = self._fake_client(self._exc(401))
        ok, err = self._probe_with(ai_gateway.PROVIDER_REPLIT, client)
        self.assertFalse(ok)
        self.assertIn("401", err)
        client.chat.completions.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
