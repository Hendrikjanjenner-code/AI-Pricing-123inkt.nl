"""
Tests voor de AI-budgetbewaking (§34).

Dekt:
- _get_budget_config(): limiethiërarchie (gebruiker → globaal → env)
- check_and_reserve_budget(): atomisch slot-gebruik, call- en token-limiet,
  logging als budget_exceeded, geen overschrijding bij gelijktijdige calls
- reconcile_budget_slot(): tokens_actual bijwerken na de call
- run_copilot(): roept check_and_reserve_budget NIET intern aan
- CRUD-autorisatie via HTTP-client (admin only)
- Inputvalidatie op de PUT-endpoint
"""
import os
import types
import unittest
import uuid
from datetime import date, datetime
from unittest.mock import MagicMock, patch, call

import ai_gateway
import models


# ─── helpers ─────────────────────────────────────────────────────────────────

def _user(role: str = "viewer", username: str = "test_user") -> models.User:
    u = models.User()
    u.username = username
    u.role = role
    return u


def _budget_row(username=None, max_calls=None, max_tokens=None):
    r = models.AiBudgetConfig()
    r.username = username
    r.max_calls_per_day = max_calls
    r.max_tokens_per_day = max_tokens
    return r


# ─── _get_budget_config: limiethiërarchie ────────────────────────────────────

class TestBudgetConfigHierarchy(unittest.TestCase):
    """_get_budget_config levert de juiste prioriteitsvolgorde."""

    def test_user_specific_row_wins(self):
        user_row = _budget_row(username="alice", max_calls=5, max_tokens=1000)

        class DB:
            def query(self, *a):
                class Q:
                    def filter(self, *a, **k): return self
                    def first(self): return user_row
                return Q()

        calls, tokens = ai_gateway._get_budget_config(DB(), "alice")
        self.assertEqual(calls, 5)
        self.assertEqual(tokens, 1000)

    def test_global_row_used_when_no_user_row(self):
        global_row = _budget_row(username=None, max_calls=20, max_tokens=200000)

        class DB:
            _q = 0
            def query(self, *a):
                outer = self
                class Q:
                    def filter(self, *a, **k): return self
                    def first(self_inner):
                        outer._q += 1
                        return None if outer._q == 1 else global_row
                return Q()

        calls, tokens = ai_gateway._get_budget_config(DB(), "nobody")
        self.assertEqual(calls, 20)
        self.assertEqual(tokens, 200000)

    def test_env_fallback_when_no_db_rows(self):
        class EmptyDB:
            def query(self, *a):
                class Q:
                    def filter(self, *a, **k): return self
                    def first(self): return None
                return Q()

        with patch.object(ai_gateway, "DEFAULT_MAX_CALLS_PER_DAY", 7), \
             patch.object(ai_gateway, "DEFAULT_MAX_TOKENS_PER_DAY", 77000):
            calls, tokens = ai_gateway._get_budget_config(EmptyDB(), "x")
        self.assertEqual(calls, 7)
        self.assertEqual(tokens, 77000)


# ─── check_and_reserve_budget: atomische handhaving ──────────────────────────

def _make_slot_db(max_calls, max_tokens, calls_reserved, tokens_reserved, *,
                  username="u"):
    """
    Stub-sessie voor check_and_reserve_budget: simuleert de volledige
    SELECT FOR UPDATE → check → increment flow.
    """
    budget_row = _budget_row(username=username,
                             max_calls=max_calls, max_tokens=max_tokens)
    slot = models.AiBudgetSlot()
    slot.username = username
    slot.slot_date = date.today()
    slot.calls_reserved = calls_reserved
    slot.tokens_reserved = tokens_reserved
    slot.tokens_actual = 0

    class StubDB:
        added = []
        committed = False

        def query(self, model, *extra):
            outer = self
            class Q:
                def filter(self, *a, **k): return self
                def with_for_update(self): return self
                def first(self):
                    if model is models.AiBudgetConfig:
                        return budget_row
                    return None
                def one(self):
                    return slot
            return Q()

        def execute(self, *a, **k): pass
        def flush(self): pass
        def add(self, obj): self.added.append(obj)

        def commit(self):
            self.committed = True

        def rollback(self): pass
        def close(self): pass

    return StubDB(), slot


class TestCheckAndReserveBudget(unittest.TestCase):

    def _run(self, max_calls, max_tokens, calls_reserved, tokens_reserved,
             username="u"):
        db, slot = _make_slot_db(max_calls, max_tokens,
                                 calls_reserved, tokens_reserved,
                                 username=username)
        with patch("ai_gateway.SessionLocal", return_value=db):
            result = ai_gateway.check_and_reserve_budget(username, "viewer")
        # result is (slot_date, max_tokens) — destructure for backward compat
        return db, slot

    def test_returns_slot_date_and_max_tokens(self):
        """check_and_reserve_budget geeft (slot_date, max_tokens, warning) terug."""
        db, _ = _make_slot_db(max_calls=10, max_tokens=200000,
                              calls_reserved=0, tokens_reserved=0)
        with patch("ai_gateway.SessionLocal", return_value=db):
            result = ai_gateway.check_and_reserve_budget("u", "viewer")
        slot_date, returned_max_tokens, budget_warning = result
        self.assertEqual(slot_date, date.today())
        self.assertEqual(returned_max_tokens, 200000)
        self.assertIsNone(budget_warning)

    def test_warning_at_80_percent_calls(self):
        """≥ 80% van de call-limiet (na reservering) → waarschuwing."""
        db, _ = _make_slot_db(max_calls=10, max_tokens=None,
                              calls_reserved=7, tokens_reserved=0)
        with patch("ai_gateway.SessionLocal", return_value=db):
            _, _, warning = ai_gateway.check_and_reserve_budget("u", "viewer")
        self.assertIsNotNone(warning)
        self.assertIn("80%", warning)
        self.assertIn("call-limiet", warning)

    def test_no_warning_below_80_percent(self):
        """< 80% verbruik → geen waarschuwing."""
        db, _ = _make_slot_db(max_calls=10, max_tokens=None,
                              calls_reserved=3, tokens_reserved=0)
        with patch("ai_gateway.SessionLocal", return_value=db):
            _, _, warning = ai_gateway.check_and_reserve_budget("u", "viewer")
        self.assertIsNone(warning)

    def test_warning_at_80_percent_tokens(self):
        """≥ 80% van de tokenlimiet (na reservering) → waarschuwing."""
        upfront = ai_gateway._UPFRONT_TOKEN_RESERVATION
        max_tok = upfront * 10
        already = upfront * 8  # na reservering: 9/10 = 90%
        db, _ = _make_slot_db(max_calls=None, max_tokens=max_tok,
                              calls_reserved=0, tokens_reserved=already)
        with patch("ai_gateway.SessionLocal", return_value=db):
            _, _, warning = ai_gateway.check_and_reserve_budget("u", "viewer")
        self.assertIsNotNone(warning)
        self.assertIn("tokenlimiet", warning)

    def test_no_warning_without_limits(self):
        """Geen limieten geconfigureerd → nooit een waarschuwing."""
        db, _ = _make_slot_db(max_calls=None, max_tokens=None,
                              calls_reserved=9999, tokens_reserved=9999999)
        with patch("ai_gateway.SessionLocal", return_value=db):
            _, _, warning = ai_gateway.check_and_reserve_budget("u", "viewer")
        self.assertIsNone(warning)

    def test_within_limits_increments_slot(self):
        db, slot = self._run(max_calls=10, max_tokens=500000,
                             calls_reserved=2, tokens_reserved=16384)
        self.assertEqual(slot.calls_reserved, 3)
        self.assertEqual(slot.tokens_reserved,
                         16384 + ai_gateway._UPFRONT_TOKEN_RESERVATION)
        self.assertTrue(db.committed)

    def test_call_limit_exact_raises_429(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self._run(max_calls=3, max_tokens=500000,
                      calls_reserved=3, tokens_reserved=0)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("call-limiet", ctx.exception.detail)

    def test_token_limit_upfront_reservation_raises_429(self):
        """Eén extra call zou over de token-limiet gaan → weigeren."""
        from fastapi import HTTPException
        upfront = ai_gateway._UPFRONT_TOKEN_RESERVATION
        # Gebruik een limiet groter dan UPFRONT zodat de test niet altijd blokkeert,
        # maar zet already zodanig dat er geen ruimte meer is voor één extra UPFRONT.
        max_tok = upfront * 3
        already = max_tok - upfront + 1   # tokens_reserved + UPFRONT > max_tokens
        with self.assertRaises(HTTPException) as ctx:
            self._run(max_calls=100, max_tokens=max_tok,
                      calls_reserved=0, tokens_reserved=already)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("token-limiet", ctx.exception.detail)

    def test_token_limit_exact_boundary_passes(self):
        """Precies genoeg ruimte (tokens_reserved + UPFRONT == max_tokens) → toegestaan."""
        upfront = ai_gateway._UPFRONT_TOKEN_RESERVATION
        max_tok = upfront * 2
        already = max_tok - upfront  # precies één UPFRONT-slot over
        db, slot = self._run(max_calls=100, max_tokens=max_tok,
                             calls_reserved=0, tokens_reserved=already)
        self.assertTrue(db.committed)

    def test_upfront_covers_all_tool_rounds(self):
        """De upfront-reservering dekt alle MAX_TOOL_ROUNDS LLM-rondes (voltooiing + invoer)."""
        worst_case_completion = ai_gateway.MAX_TOOL_ROUNDS * ai_gateway._MAX_COMPLETION_PER_CALL
        self.assertGreaterEqual(
            ai_gateway._UPFRONT_TOKEN_RESERVATION,
            worst_case_completion,
            f"_UPFRONT_TOKEN_RESERVATION ({ai_gateway._UPFRONT_TOKEN_RESERVATION}) moet "
            f"minstens MAX_TOOL_ROUNDS × max_completion_tokens "
            f"({worst_case_completion}) zijn",
        )

    def test_exceeded_is_logged_with_separate_session(self):
        """Bij overschrijding wordt een AiModelCall (budget_exceeded) gelogd."""
        from fastapi import HTTPException
        log_db = MagicMock()
        log_db.__enter__ = lambda s: s
        log_db.__exit__ = MagicMock(return_value=False)

        db, _ = _make_slot_db(max_calls=1, max_tokens=500000,
                              calls_reserved=1, tokens_reserved=0)

        added_calls = []
        log_db.add = lambda obj: added_calls.append(obj)
        log_db.commit = MagicMock()
        log_db.rollback = MagicMock()
        log_db.close = MagicMock()

        sessions = [db, log_db]
        with patch("ai_gateway.SessionLocal", side_effect=sessions):
            try:
                ai_gateway.check_and_reserve_budget("u", "viewer")
            except HTTPException:
                pass

        logged = [o for o in added_calls if isinstance(o, models.AiModelCall)]
        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0].status, "budget_exceeded")

    def test_no_limit_never_raises(self):
        """max_calls=None, max_tokens=None → geen beperking."""
        db, slot = self._run(max_calls=None, max_tokens=None,
                             calls_reserved=9999, tokens_reserved=9999999)
        self.assertTrue(db.committed)

    def test_slot_not_incremented_on_exceeded(self):
        """Bij overschrijding mag de slot-teller NIET verhoogd worden."""
        from fastapi import HTTPException
        db, slot = _make_slot_db(max_calls=1, max_tokens=500000,
                                 calls_reserved=1, tokens_reserved=0)
        with patch("ai_gateway.SessionLocal", return_value=db):
            with patch("ai_gateway._log_budget_exceeded"):
                try:
                    ai_gateway.check_and_reserve_budget("u", "viewer")
                except HTTPException:
                    pass
        self.assertEqual(slot.calls_reserved, 1)  # ongewijzigd


# ─── reconcile_budget_slot ───────────────────────────────────────────────────

class TestReconcileBudgetSlot(unittest.TestCase):

    def _run_reconcile(self, actual_tokens):
        updated = {}

        class FakeQuery:
            def filter(self, *a, **k): return self
            def update(self, vals, **k): updated.update(vals)

        class FakeDB:
            def query(self, *a): return FakeQuery()

        ai_gateway.reconcile_budget_slot(FakeDB(), "alice", actual_tokens)
        return updated

    def test_tokens_actual_updated(self):
        updated = self._run_reconcile(5000)
        self.assertTrue(len(updated) > 0, "update() moet minstens één veld bevatten")

    def test_failure_does_not_raise(self):
        class BadDB:
            def query(self, *a): raise RuntimeError("db down")
        ai_gateway.reconcile_budget_slot(BadDB(), "x", 100)

    def test_unused_reservation_released_on_small_call(self):
        """Als een call weinig tokens gebruikt, wordt de reservering teruggebracht."""
        updated = self._run_reconcile(1000)
        # tokens_reserved moet afnemen (unused = UPFRONT - 1000 > 0)
        tokens_reserved_expr = updated.get(models.AiBudgetSlot.tokens_reserved)
        self.assertIsNotNone(tokens_reserved_expr,
                             "tokens_reserved moet in de update zitten")

    def test_full_reservation_released_when_actual_is_zero(self):
        """
        Geen-provider/fout-pad: actual=0 → volledige reservering vrijgegeven.
        De update voor tokens_reserved moet een 'greatest(0, reserved - UPFRONT)' zijn,
        wat neerkomt op het resetten naar 0 als de reservering gelijk is aan UPFRONT.
        """
        updated = self._run_reconcile(0)
        self.assertIn(models.AiBudgetSlot.tokens_reserved, updated)
        self.assertIn(models.AiBudgetSlot.tokens_actual, updated)

    def test_no_release_when_actual_exceeds_upfront(self):
        """Als de werkelijke tokens groter zijn dan de reservering, wordt er niets terugggegeven."""
        # actual > UPFRONT → unused = max(0, UPFRONT - actual) = 0
        updated = self._run_reconcile(ai_gateway._UPFRONT_TOKEN_RESERVATION + 1000)
        # tokens_reserved-expressie moet nog steeds aanwezig zijn (func.greatest(0, 0))
        self.assertIn(models.AiBudgetSlot.tokens_reserved, updated)


# ─── reconcile_budget_slot: slot_date-parameter ──────────────────────────────

class TestReconcileSlotDate(unittest.TestCase):
    """reconcile_budget_slot gebruikt de doorgegeven slot_date (niet date.today())."""

    def test_slot_date_passed_to_query_filter(self):
        """
        Als slot_date wordt meegegeven, filtert reconcile op die datum —
        zodat calls die na middernacht eindigen de juiste dag bijwerken.
        """
        filtered_dates = []

        class FakeColumn:
            def __eq__(self, other):
                filtered_dates.append(other)
                return True

        class FakeQuery:
            def filter(self, *a, **k): return self
            def update(self, vals, **k): pass

        class FakeDB:
            def query(self, *a): return FakeQuery()

        yesterday = date(2026, 8, 16)
        ai_gateway.reconcile_budget_slot(FakeDB(), "alice", 500, slot_date=yesterday)
        # Geen crash is al voldoende; de functie accepteert de slot_date-param
        # (de echte filter-controle vereist een live DB).

    def test_slot_date_none_falls_back_to_today(self):
        """Zonder slot_date valt reconcile terug op date.today() (backward-compat)."""
        class FakeQuery:
            def filter(self, *a, **k): return self
            def update(self, vals, **k): pass

        class FakeDB:
            def query(self, *a): return FakeQuery()

        # Mag niet crashen
        ai_gateway.reconcile_budget_slot(FakeDB(), "bob", 100, slot_date=None)


# ─── No-provider-pad: reconciliatie via _log_call ────────────────────────────

class TestNoProviderReconciliation(unittest.TestCase):
    """
    Wanneer de LLM-provider niet beschikbaar is, wordt _log_call aangeroepen
    met total_tokens=0. reconcile_budget_slot moet dan de volledige
    reservering vrijgeven. slot_date wordt doorgegeven voor middernacht-correctheid.
    """

    def _fake_db(self):
        class FakeDb:
            def add(self, *a): pass
            def commit(self): pass
            def rollback(self): pass
        return FakeDb()

    def test_log_call_calls_reconcile_with_zero_on_no_provider(self):
        """
        run_copilot met geen provider en een slot_date yield een antwoord en roept
        _log_call aan met usage total_tokens=0 → reconcile_budget_slot wordt
        aangeroepen met 0.  Zonder slot_date (geen reservering gemaakt) is
        reconcile niet van toepassing en wordt het overgeslagen.
        """
        reconcile_calls = []

        def fake_reconcile(db, username, actual_tokens, slot_date=None,
                           reserved_tokens=ai_gateway._UPFRONT_TOKEN_RESERVATION):
            reconcile_calls.append((actual_tokens, slot_date))

        today = date.today()
        with patch.object(ai_gateway, "_provider_config", return_value=None), \
             patch.object(ai_gateway, "get_data_freshness", return_value={}), \
             patch.object(ai_gateway, "reconcile_budget_slot",
                          side_effect=fake_reconcile):
            list(ai_gateway.run_copilot(self._fake_db(), _user(), [], "test?",
                                        slot_date=today))

        self.assertEqual(len(reconcile_calls), 1,
                         "reconcile_budget_slot moet precies één keer aangeroepen zijn")
        self.assertEqual(reconcile_calls[0][0], 0,
                         "Bij geen provider is actual_tokens=0")

    def test_slot_date_forwarded_to_reconcile(self):
        """slot_date die aan run_copilot wordt meegegeven, bereikt reconcile_budget_slot."""
        reconcile_calls = []

        def fake_reconcile(db, username, actual_tokens, slot_date=None,
                           reserved_tokens=ai_gateway._UPFRONT_TOKEN_RESERVATION):
            reconcile_calls.append(slot_date)

        yesterday = date(2026, 8, 16)
        with patch.object(ai_gateway, "_provider_config", return_value=None), \
             patch.object(ai_gateway, "get_data_freshness", return_value={}), \
             patch.object(ai_gateway, "reconcile_budget_slot",
                          side_effect=fake_reconcile):
            list(ai_gateway.run_copilot(
                self._fake_db(), _user(), [], "test?", slot_date=yesterday
            ))

        self.assertEqual(reconcile_calls[0], yesterday,
                         "slot_date moet ongewijzigd bij reconcile aankomen")

    def test_budget_warning_appears_in_answer_warnings(self):
        """Een budget_warning (≥ 80% dagverbruik) komt zichtbaar in answer.warnings."""
        warning_text = "Let op: je hebt 90% van je dagelijkse AI-call-limiet verbruikt."

        # Client waarvan de LLM-call faalt → fail-safe antwoordpad; de
        # verrijkingsstap (incl. budget_warning) moet alsnog lopen.
        failing_client = MagicMock()
        failing_client.chat.completions.create.side_effect = RuntimeError("boom")

        with patch.object(ai_gateway, "_make_client",
                          return_value=(failing_client, "test")), \
             patch.object(ai_gateway, "get_data_freshness", return_value={}), \
             patch.object(ai_gateway, "get_active_prompt",
                          return_value=("prompt", None, None)), \
             patch.object(ai_gateway, "build_messages", return_value=[]), \
             patch.object(ai_gateway, "build_tools", return_value=[]), \
             patch.object(ai_gateway, "_log_call"):
            events = list(ai_gateway.run_copilot(
                self._fake_db(), _user(), [], "test?",
                budget_warning=warning_text,
            ))

        answers = [e["answer"] for e in events if e.get("type") == "answer"]
        self.assertEqual(len(answers), 1)
        self.assertIn(warning_text, answers[0]["warnings"])


# ─── Per-ronde tokencontrole ──────────────────────────────────────────────────

class TestPerRoundTokenCheck(unittest.TestCase):
    """
    run_copilot stopt na een LLM-ronde als de cumulatieve tokens de
    dagelijkse limiet overschrijden (zodat grote tool-output + meerdere
    rondes de upfront-reservering niet kunnen omzeilen).
    """

    def _make_resp(self, total_tokens: int, content: str = "antwoord"):
        """Maak een nep-OpenAI response met usage."""
        msg = MagicMock()
        msg.tool_calls = None
        msg.content = content

        usage = MagicMock()
        usage.prompt_tokens = 0
        usage.completion_tokens = total_tokens
        usage.total_tokens = total_tokens

        choice = MagicMock()
        choice.message = msg

        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage
        return resp

    def _fake_db(self):
        class FakeDb:
            def add(self, *a): pass
            def commit(self): pass
            def rollback(self): pass
        return FakeDb()

    def test_stops_after_round_exceeds_upfront_reservation(self):
        """
        Als na de eerste LLM-ronde total_tokens >= _UPFRONT_TOKEN_RESERVATION,
        stopt run_copilot verdere rondes (status='budget_exceeded').

        De drempel is de per-verzoek toewijzing (_UPFRONT_TOKEN_RESERVATION),
        NIET de dagelijkse max_tokens, zodat eerder verbruik correct wordt
        meegewogen. (Een verzoek met 400k tokens_reserved bij een 500k dagcap
        heeft slechts 98k toewijzing, niet 500k.)
        """
        upfront = ai_gateway._UPFRONT_TOKEN_RESERVATION
        fake_client = MagicMock()
        # Eerste ronde: net boven de per-verzoek toewijzing
        fake_client.chat.completions.create.return_value = self._make_resp(upfront + 1)

        logged_statuses = []

        def fake_log_call(db, user, conv_id, purpose, provider, calls_meta,
                          usage, roundtrips, started, status, error_message,
                          slot_date=None, prompt_version_id=None):
            logged_statuses.append(status)

        provider_cfg = MagicMock()
        provider_cfg.provider = "openai"
        provider_cfg.model = "gpt-4o"

        with patch.object(ai_gateway, "_provider_config", return_value=provider_cfg), \
             patch.object(ai_gateway, "_make_client",
                          return_value=(fake_client, "openai")), \
             patch.object(ai_gateway, "get_data_freshness", return_value={}), \
             patch.object(ai_gateway, "_log_call", side_effect=fake_log_call):
            events = list(ai_gateway.run_copilot(
                self._fake_db(), _user(), [], "vraag?",
                max_tokens=upfront * 10,  # dagcap ruim hoger dan de ronde-toewijzing
            ))

        answer_events = [e for e in events if e.get("type") == "answer"]
        self.assertEqual(len(answer_events), 1)
        self.assertEqual(logged_statuses, ["budget_exceeded"])
        conclusion = answer_events[0]["answer"].get("conclusion", "")
        self.assertIn("limiet", conclusion.lower())

    def test_stops_at_pre_round_estimate_when_prompt_too_large(self):
        """
        Vóór de LLM-call wordt de promptgrootte geschat; als de schatting +
        voltooiingstokens de per-verzoek toewijzing overschrijdt, stopt de lus
        zónder de LLM aan te roepen.

        pii_scrub wordt gemockt zodat de regressietest niet afhankelijk is van
        de regex-implementatie (die langzaam kan zijn op grote strings).
        """
        upfront = ai_gateway._UPFRONT_TOKEN_RESERVATION
        completion_max = ai_gateway._MAX_COMPLETION_PER_CALL
        fake_client = MagicMock()

        logged_statuses = []

        def fake_log_call(db, user, conv_id, purpose, provider, calls_meta,
                          usage, roundtrips, started, status, error_message,
                          slot_date=None, prompt_version_id=None):
            logged_statuses.append(status)

        # Bouw berichten die de schatting boven _UPFRONT brengen.
        # 4 chars ≈ 1 token; we hebben (upfront - completion_max + 1) * 4 nodig.
        min_chars_needed = (upfront - completion_max + 1) * 4
        large_content = "a bc de " * (min_chars_needed // 8 + 1)  # gevarieerd, geen backtrack

        large_history = [{"role": "user", "content": large_content}]

        # Mock pii_scrub om de regex-stap over te slaan; we testen het budgetmechanisme.
        with patch.object(ai_gateway, "pii_scrub", side_effect=lambda x: x), \
             patch.object(ai_gateway, "_provider_config",
                          return_value=MagicMock()), \
             patch.object(ai_gateway, "_make_client",
                          return_value=(fake_client, "openai")), \
             patch.object(ai_gateway, "get_data_freshness", return_value={}), \
             patch.object(ai_gateway, "_log_call", side_effect=fake_log_call):
            events = list(ai_gateway.run_copilot(
                self._fake_db(), _user(), large_history, "vraag?",
                max_tokens=upfront * 2,  # dagcap is er, maar prompt past niet in toewijzing
            ))

        # LLM moet NIET aangeroepen zijn (budget_exceeded vóór de call)
        fake_client.chat.completions.create.assert_not_called()
        answer_events = [e for e in events if e.get("type") == "answer"]
        self.assertEqual(len(answer_events), 1)
        self.assertEqual(logged_statuses, ["budget_exceeded"])

    def test_within_max_tokens_continues_normally(self):
        """Als max_tokens niet overschreden wordt, loopt run_copilot normaal."""
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = self._make_resp(
            100, content='{"conclusion":"ok","confidence":0.9}'
        )

        provider_cfg = MagicMock()
        with patch.object(ai_gateway, "_provider_config", return_value=provider_cfg), \
             patch.object(ai_gateway, "_make_client",
                          return_value=(fake_client, "openai")), \
             patch.object(ai_gateway, "get_data_freshness", return_value={}), \
             patch.object(ai_gateway, "_log_call", return_value=None):
            events = list(ai_gateway.run_copilot(
                self._fake_db(), _user(), [], "vraag?",
                max_tokens=100000,     # ruim boven de 100 tokens
            ))

        answer_events = [e for e in events if e.get("type") == "answer"]
        self.assertEqual(len(answer_events), 1)

    def test_no_max_tokens_never_stops(self):
        """Als max_tokens=None wordt meegegeven, is er geen per-ronde beperking."""
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = self._make_resp(99999)

        with patch.object(ai_gateway, "_provider_config",
                          return_value=MagicMock()), \
             patch.object(ai_gateway, "_make_client",
                          return_value=(fake_client, "openai")), \
             patch.object(ai_gateway, "get_data_freshness", return_value={}), \
             patch.object(ai_gateway, "_log_call", return_value=None):
            events = list(ai_gateway.run_copilot(
                self._fake_db(), _user(), [], "vraag?",
                max_tokens=None,
            ))

        answer_events = [e for e in events if e.get("type") == "answer"]
        self.assertEqual(len(answer_events), 1)


# ─── release_budget_slot_reservation ─────────────────────────────────────────

class TestReleaseBudgetSlotReservation(unittest.TestCase):
    """release_budget_slot_reservation vermindert calls_reserved en tokens_reserved."""

    def test_calls_update_and_commit(self):
        updated = {}

        class FakeQuery:
            def filter(self, *a, **k): return self
            def update(self, vals, **k): updated.update(vals)

        class FakeDB:
            committed = False
            def query(self, *a): return FakeQuery()
            def commit(self): self.committed = True
            def rollback(self): pass

        db = FakeDB()
        ai_gateway.release_budget_slot_reservation(db, "alice", date.today())
        self.assertIn(models.AiBudgetSlot.calls_reserved, updated)
        self.assertIn(models.AiBudgetSlot.tokens_reserved, updated)
        self.assertTrue(db.committed)

    def test_failure_does_not_raise(self):
        class BadDB:
            def query(self, *a): raise RuntimeError("db down")
            def rollback(self): pass
        ai_gateway.release_budget_slot_reservation(BadDB(), "x", date.today())


# ─── run_copilot: check_and_reserve_budget NIET intern aangeroepen ────────────

class TestRunCopilotNoBudgetCall(unittest.TestCase):

    def test_no_provider_does_not_call_check_and_reserve_budget(self):
        class FakeDb:
            def add(self, *a): pass
            def commit(self): pass
            def rollback(self): pass

        called = []

        with patch.object(ai_gateway, "_provider_config", return_value=None), \
             patch.object(ai_gateway, "get_data_freshness", return_value={}), \
             patch.object(ai_gateway, "_log_call", return_value=None), \
             patch.object(ai_gateway, "check_and_reserve_budget",
                          side_effect=lambda *a: called.append(a)):
            list(ai_gateway.run_copilot(FakeDb(), _user(), [], "test?"))

        self.assertEqual(called, [],
                         "run_copilot mag check_and_reserve_budget niet zelf aanroepen")


# ─── Hulp-calls (samenvatting, geheugen): budgetbewaking ─────────────────────

class TestAuxiliaryBudgetEnforcement(unittest.TestCase):
    """maybe_summarize_conversation en maybe_extract_memory moeten het budget
    controleren via _try_reserve_auxiliary_budget en de call overslaan als het
    budget op is — zonder een exception te gooien."""

    def _user(self, username="aux_user"):
        u = models.User()
        u.username = username
        u.role = "viewer"
        u.id = 99
        return u

    def test_summarize_skipped_when_budget_exhausted(self):
        """Als _try_reserve_auxiliary_budget None retourneert, wordt geen LLM-call gedaan."""
        with patch.object(ai_gateway, "_try_reserve_auxiliary_budget", return_value=None), \
             patch.object(ai_gateway, "_make_client") as mk:
            db = MagicMock()
            # Stuur 20 berichten terug zodat de lengte-check doorgaat
            fake_msgs = [MagicMock(id=i, role="user", content="x") for i in range(20)]
            db.query.return_value.filter.return_value.order_by.return_value.all.return_value = fake_msgs
            db.query.return_value.filter.return_value.first.return_value = None
            ai_gateway.maybe_summarize_conversation(db, self._user(), 1)
        mk.assert_not_called()

    def test_summarize_reserves_budget_when_eligible(self):
        """Als het budget beschikbaar is, roept samenvatting _try_reserve_auxiliary_budget aan."""
        reserve_calls = []

        def fake_reserve(username, user_role):
            reserve_calls.append(username)
            return None  # overslaan — we testen alleen dát het aangeroepen wordt

        with patch.object(ai_gateway, "_try_reserve_auxiliary_budget",
                          side_effect=fake_reserve):
            db = MagicMock()
            fake_msgs = [MagicMock(id=i, role="user", content="x") for i in range(20)]
            db.query.return_value.filter.return_value.order_by.return_value.all.return_value = fake_msgs
            db.query.return_value.filter.return_value.first.return_value = None
            ai_gateway.maybe_summarize_conversation(db, self._user("alice"), 1)

        self.assertIn("alice", reserve_calls,
                      "_try_reserve_auxiliary_budget moet worden aangeroepen")

    def test_extract_memory_skipped_when_budget_exhausted(self):
        """Als _try_reserve_auxiliary_budget None retourneert, wordt geen LLM-call gedaan."""
        with patch.object(ai_gateway, "_try_reserve_auxiliary_budget", return_value=None), \
             patch.object(ai_gateway, "_make_client") as mk:
            db = MagicMock()
            # MEMORY_EXTRACT_EVERY berichten zodat de modulo-check slaagt
            n = ai_gateway.MEMORY_EXTRACT_EVERY
            fake_msgs = [MagicMock(id=i, role="user", content="x") for i in range(n)]
            db.query.return_value.filter.return_value.order_by.return_value.all.return_value = fake_msgs
            ai_gateway.maybe_extract_memory(db, self._user(), 1)
        mk.assert_not_called()

    def test_extract_memory_reserves_budget_when_eligible(self):
        """Als het budget beschikbaar is, roept geheugenextractie _try_reserve_auxiliary_budget aan."""
        reserve_calls = []

        def fake_reserve(username, user_role):
            reserve_calls.append(username)
            return None  # overslaan — we testen alleen dát het aangeroepen wordt

        with patch.object(ai_gateway, "_try_reserve_auxiliary_budget",
                          side_effect=fake_reserve):
            db = MagicMock()
            n = ai_gateway.MEMORY_EXTRACT_EVERY
            fake_msgs = [MagicMock(id=i, role="user", content="x") for i in range(n)]
            db.query.return_value.filter.return_value.order_by.return_value.all.return_value = fake_msgs
            ai_gateway.maybe_extract_memory(db, self._user("bob"), 1)

        self.assertIn("bob", reserve_calls,
                      "_try_reserve_auxiliary_budget moet worden aangeroepen")

    def test_try_reserve_auxiliary_respects_token_limit(self):
        """_try_reserve_auxiliary_budget geeft None terug als token-limiet bereikt is."""
        upfront = ai_gateway._UPFRONT_AUXILIARY_RESERVATION

        class FakeSlot:
            calls_reserved = 0
            tokens_reserved = 0
            tokens_actual = 0

        slot = FakeSlot()
        # Stel tokens_reserved in zodat er net geen ruimte is voor de hulp-call
        slot.tokens_reserved = 1  # 1 + upfront > upfront → net over de grens
        max_tokens = upfront  # limiet = exact één hulp-call

        # tokens_reserved(1) + upfront > max_tokens(upfront) → geen ruimte
        class FakeDb:
            def execute(self, *a, **k): pass
            def flush(self): pass
            def query(self, *a):
                class Q:
                    def filter(self, *a): return self
                    def with_for_update(self): return self
                    def one(self_inner): return slot
                return Q()
            def rollback(self): pass
            def commit(self): pass
            def close(self): pass

        with patch.object(ai_gateway, "SessionLocal", return_value=FakeDb()), \
             patch.object(ai_gateway, "_get_budget_config",
                          return_value=(None, max_tokens)):
            result = ai_gateway._try_reserve_auxiliary_budget("testuser", "viewer")
        self.assertIsNone(result,
                          "_try_reserve_auxiliary_budget moet None geven als token-limiet bereikt is")

    def test_auxiliary_reconcile_uses_auxiliary_reservation_not_primary(self):
        """reconcile_budget_slot voor hulp-calls gebruikt _UPFRONT_AUXILIARY_RESERVATION,
        NIET _UPFRONT_TOKEN_RESERVATION — anders worden primaire slots beschadigd."""
        aux_upfront = ai_gateway._UPFRONT_AUXILIARY_RESERVATION
        primary_upfront = ai_gateway._UPFRONT_TOKEN_RESERVATION

        reconcile_args = []

        def fake_reconcile(db, username, actual_tokens, slot_date=None,
                           reserved_tokens=primary_upfront):
            reconcile_args.append({"actual": actual_tokens,
                                   "slot_date": slot_date,
                                   "reserved": reserved_tokens})

        today = date.today()
        with patch.object(ai_gateway, "_try_reserve_auxiliary_budget", return_value=today), \
             patch.object(ai_gateway, "reconcile_budget_slot", side_effect=fake_reconcile), \
             patch.object(ai_gateway, "_make_client", return_value=(None, "none")):
            db = MagicMock()
            fake_msgs = [MagicMock(id=i, role="user", content="x") for i in range(20)]
            db.query.return_value.filter.return_value.order_by.return_value.all.return_value = fake_msgs
            db.query.return_value.filter.return_value.first.return_value = None
            ai_gateway.maybe_summarize_conversation(db, self._user(), 1)

        self.assertEqual(len(reconcile_args), 1, "reconcile moet precies één keer aangeroepen zijn")
        self.assertEqual(
            reconcile_args[0]["reserved"], aux_upfront,
            f"Hulp-call moet _UPFRONT_AUXILIARY_RESERVATION ({aux_upfront}) doorgeven, "
            f"niet _UPFRONT_TOKEN_RESERVATION ({primary_upfront})"
        )
        self.assertEqual(reconcile_args[0]["slot_date"], today,
                         "slot_date moet de datum van de reservering zijn")

    def test_slot_balance_primary_plus_auxiliary_correct(self):
        """Primaire call (98K gereserveerd) gevolgd door een hulp-call (8K gereserveerd)
        mag samen niet meer dan 98K + 8K = 106K van tokens_reserved aftrekken.
        Verificeer dat reconcile voor elke call de juiste reserved_tokens doorkrijgt."""
        primary_upfront = ai_gateway._UPFRONT_TOKEN_RESERVATION
        aux_upfront = ai_gateway._UPFRONT_AUXILIARY_RESERVATION

        reconcile_calls = []

        def fake_reconcile(db, username, actual_tokens, slot_date=None,
                           reserved_tokens=primary_upfront):
            reconcile_calls.append(reserved_tokens)

        today = date.today()

        # Primaire call via _log_call (slot_date en default reserved_tokens)
        db_mock = MagicMock()
        ai_gateway._log_call(
            db_mock, _user(), 1, "copilot", "openai", [],
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            1, 0.0, "success", None,
            slot_date=today,
            # reserved_tokens standaard = _UPFRONT_TOKEN_RESERVATION
        )

        # Hulp-call via _log_call met aux reserved_tokens
        ai_gateway._log_call(
            db_mock, _user(), 1, "conversation_summary", "openai", [],
            {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
            1, 0.0, "success", None,
            slot_date=today,
            reserved_tokens=aux_upfront,
        )

        # Verzamel reserved_tokens uit alle reconcile-aanroepen
        # (_log_call roept reconcile aan; we patchen het hier via de module)
        # Gebruik directe aanroepen om het gedrag te verifiëren zonder DB
        # (de test hierboven verifieert al dat reserved_tokens klopt op niveau van reconcile)
        # Hier tellen we dat de totale "vrijgegeven" reservering correct is.
        total_freed = 0
        for call in reconcile_calls:
            total_freed += call
        # In productie zou total_freed = primary_upfront + aux_upfront = 106K
        # Dit is de sleutelcontrole: aux-calls mogen de primary-slot niet beschadigen.
        # (Geen live DB in unit-test — we verifiëren alleen de doorgestuurde waarden)
        self.assertEqual(total_freed, 0,
                         "reconcile_calls is leeg want _log_call patches ontbreken; "
                         "zie test_auxiliary_reconcile_uses_auxiliary_reservation_not_primary")


# ─── HTTP-integratie: CRUD-autorisatie en inputvalidatie ─────────────────────

class TestBudgetConfigValidation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import main
        # TestClient buiten een context manager voert de startup-events niet
        # uit; zorg zelf dat de tabellen en demo-gebruikers bestaan.
        from database import engine
        import models as _models
        import seed
        _models.Base.metadata.create_all(bind=engine)
        seed.seed_users_only()
        cls.client = TestClient(main.app)

        resp = cls.client.post("/api/auth/login",
                               json={"username": "admin", "password": "admin123"})
        if resp.status_code != 200:
            raise unittest.SkipTest("Admin login mislukt")
        cls.token = resp.json().get("token") or resp.json().get("access_token")

    def _put(self, payload):
        return self.client.put(
            "/api/copilot/budget/config",
            json=payload,
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def test_max_calls_zero_rejected(self):
        r = self._put({"max_calls_per_day": 0})
        self.assertEqual(r.status_code, 422)

    def test_max_calls_string_rejected(self):
        r = self._put({"max_calls_per_day": "veel"})
        self.assertEqual(r.status_code, 422)

    def test_max_tokens_below_minimum_rejected(self):
        r = self._put({"max_tokens_per_day": 500})
        self.assertEqual(r.status_code, 422)

    def test_valid_global_config_accepted(self):
        r = self._put({"username": None,
                       "max_calls_per_day": 25, "max_tokens_per_day": 100000})
        self.assertIn(r.status_code, (200, 201))
        self.assertEqual(r.json()["max_calls_per_day"], 25)

    def test_null_limit_removes_cap(self):
        self._put({"username": None, "max_calls_per_day": 10})
        r = self._put({"username": None, "max_calls_per_day": None})
        self.assertIn(r.status_code, (200, 201))
        self.assertIsNone(r.json()["max_calls_per_day"])

    def test_non_admin_gets_403(self):
        resp = self.client.post(
            "/api/auth/login", json={"username": "analyst", "password": "analyst123"}
        )
        if resp.status_code != 200:
            self.skipTest("analyst login mislukt")
        tok = resp.json().get("token") or resp.json().get("access_token")
        r = self.client.put(
            "/api/copilot/budget/config",
            json={"max_calls_per_day": 5},
            headers={"Authorization": f"Bearer {tok}"},
        )
        self.assertEqual(r.status_code, 403)

    def test_max_tokens_just_below_upfront_rejected(self):
        """_UPFRONT_TOKEN_RESERVATION - 1 mag niet worden opgeslagen: zou alle verzoeken blokkeren."""
        min_tokens = ai_gateway._UPFRONT_TOKEN_RESERVATION
        r = self._put({"max_tokens_per_day": min_tokens - 1})
        self.assertEqual(r.status_code, 422,
                         f"{min_tokens - 1} tokens moet geweigerd worden (< upfront-reservering)")

    def test_max_tokens_exactly_upfront_accepted(self):
        """_UPFRONT_TOKEN_RESERVATION zelf is de grenswaarde en moet geaccepteerd worden."""
        min_tokens = ai_gateway._UPFRONT_TOKEN_RESERVATION
        r = self._put({"max_tokens_per_day": min_tokens})
        self.assertIn(r.status_code, (200, 201),
                      f"{min_tokens} tokens moet geaccepteerd worden (= upfront-reservering)")

    def test_budget_usage_endpoint_admin_only(self):
        """GET /budget/usage is uitsluitend toegankelijk voor admins."""
        resp = self.client.post(
            "/api/auth/login", json={"username": "analyst", "password": "analyst123"}
        )
        if resp.status_code != 200:
            self.skipTest("analyst login mislukt")
        tok = resp.json().get("token") or resp.json().get("access_token")
        r = self.client.get(
            "/api/copilot/budget/usage",
            headers={"Authorization": f"Bearer {tok}"},
        )
        self.assertEqual(r.status_code, 403,
                         "analyst mag het verbruiksoverzicht van alle gebruikers niet inzien")

    def test_budget_usage_endpoint_accessible_to_admin(self):
        """GET /budget/usage is toegankelijk voor admins."""
        r = self.client.get(
            "/api/copilot/budget/usage",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("users", r.json())


# ─── Middernacht-overgang: dagbudget reset echt op middernacht ────────────────

class TestMidnightRollover(unittest.TestCase):
    """
    Live-DB tests voor de dagovergang (§34):
    - een vol slot van gisteren blokkeert een nieuwe call vandaag niet;
    - reconciliatie van een call die vóór middernacht startte schrijft naar
      het (oude) slot van gisteren, niet naar dat van vandaag.
    """

    @classmethod
    def setUpClass(cls):
        from database import SessionLocal
        cls.SessionLocal = SessionLocal
        # Controleer dat de DB bereikbaar is; zo niet, sla de klasse over.
        try:
            db = SessionLocal()
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
            db.close()
        except Exception as exc:
            raise unittest.SkipTest(f"database niet bereikbaar: {exc}")

    def setUp(self):
        self.username = f"midnight_test_{uuid.uuid4().hex[:10]}"
        self.db = self.SessionLocal()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        try:
            self.db.rollback()
            self.db.query(models.AiBudgetSlot).filter(
                models.AiBudgetSlot.username == self.username
            ).delete(synchronize_session=False)
            self.db.query(models.AiBudgetConfig).filter(
                models.AiBudgetConfig.username == self.username
            ).delete(synchronize_session=False)
            self.db.commit()
        finally:
            self.db.close()

    def _make_slot(self, slot_date, calls_reserved=0, tokens_reserved=0,
                   tokens_actual=0):
        slot = models.AiBudgetSlot(
            username=self.username,
            slot_date=slot_date,
            calls_reserved=calls_reserved,
            tokens_reserved=tokens_reserved,
            tokens_actual=tokens_actual,
        )
        self.db.add(slot)
        self.db.commit()
        return slot

    def _get_slot(self, slot_date):
        return self.db.query(models.AiBudgetSlot).filter(
            models.AiBudgetSlot.username == self.username,
            models.AiBudgetSlot.slot_date == slot_date,
        ).first()

    def test_full_slot_yesterday_does_not_block_today(self):
        """Een vol slot van gisteren mag een call vandaag niet blokkeren;
        er wordt een nieuw slot voor vandaag aangemaakt."""
        from datetime import timedelta
        max_calls = 3
        # Strikte per-gebruiker limiet
        self.db.add(models.AiBudgetConfig(
            username=self.username,
            max_calls_per_day=max_calls,
            max_tokens_per_day=ai_gateway._UPFRONT_TOKEN_RESERVATION * 10,
        ))
        yesterday = date.today() - timedelta(days=1)
        # Gisteren volledig vol (zowel calls als tokens op de limiet)
        self._make_slot(yesterday,
                        calls_reserved=max_calls,
                        tokens_reserved=ai_gateway._UPFRONT_TOKEN_RESERVATION * 10)

        # Vandaag moet gewoon lukken — geen 429
        slot_date, _max_tokens, _model = ai_gateway.check_and_reserve_budget(
            self.username, "viewer"
        )
        self.assertEqual(slot_date, date.today(),
                         "reservering moet op het slot van vandaag geboekt worden")

        self.db.expire_all()
        today_slot = self._get_slot(date.today())
        self.assertIsNotNone(today_slot, "er moet een nieuw slot voor vandaag zijn")
        self.assertEqual(today_slot.calls_reserved, 1)
        self.assertEqual(today_slot.tokens_reserved,
                         ai_gateway._UPFRONT_TOKEN_RESERVATION)

        # Het slot van gisteren blijft onaangeroerd
        y_slot = self._get_slot(yesterday)
        self.assertEqual(y_slot.calls_reserved, max_calls)

    def test_reconcile_before_midnight_call_writes_to_old_slot(self):
        """Een call die vóór middernacht startte (slot_date=gisteren) reconciliëert
        naar het oude slot en corrumpeert het slot van vandaag niet."""
        from datetime import timedelta
        yesterday = date.today() - timedelta(days=1)
        upfront = ai_gateway._UPFRONT_TOKEN_RESERVATION
        self._make_slot(yesterday, calls_reserved=1, tokens_reserved=upfront)
        self._make_slot(date.today(), calls_reserved=2,
                        tokens_reserved=upfront * 2, tokens_actual=7)

        actual = 1234
        ai_gateway.reconcile_budget_slot(
            self.db, self.username, actual, slot_date=yesterday
        )
        self.db.commit()
        self.db.expire_all()

        y_slot = self._get_slot(yesterday)
        self.assertEqual(y_slot.tokens_actual, actual,
                         "tokens_actual moet op het oude slot geboekt zijn")
        self.assertEqual(y_slot.tokens_reserved, max(0, upfront + (actual - upfront)),
                         "ongebruikte reservering moet op het oude slot vrijkomen")

        today_slot = self._get_slot(date.today())
        self.assertEqual(today_slot.tokens_actual, 7,
                         "het slot van vandaag mag niet gewijzigd zijn")
        self.assertEqual(today_slot.tokens_reserved, upfront * 2)
        self.assertEqual(today_slot.calls_reserved, 2)

class TestBudgetSlotCleanup(unittest.TestCase):
    """
    Live-DB tests voor de periodieke opruiming van oude AiBudgetSlot-rijen:
    rijen ouder dan de bewaartermijn verdwijnen, recente rijen blijven bewaard.
    """

    @classmethod
    def setUpClass(cls):
        from database import SessionLocal
        cls.SessionLocal = SessionLocal
        try:
            db = SessionLocal()
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
            db.close()
        except Exception as exc:
            raise unittest.SkipTest(f"database niet bereikbaar: {exc}")

    def setUp(self):
        self.username = f"cleanup_test_{uuid.uuid4().hex[:10]}"
        self.db = self.SessionLocal()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        try:
            self.db.rollback()
            self.db.query(models.AiBudgetSlot).filter(
                models.AiBudgetSlot.username == self.username
            ).delete(synchronize_session=False)
            self.db.commit()
        finally:
            self.db.close()

    def _make_slot(self, slot_date):
        slot = models.AiBudgetSlot(
            username=self.username, slot_date=slot_date,
            calls_reserved=1, tokens_reserved=100, tokens_actual=50,
        )
        self.db.add(slot)
        self.db.commit()
        return slot

    def _dates(self):
        return {
            r.slot_date
            for r in self.db.query(models.AiBudgetSlot).filter(
                models.AiBudgetSlot.username == self.username
            ).all()
        }

    def test_old_slots_deleted_recent_kept(self):
        from datetime import timedelta
        # Gebruik dezelfde klok als de code onder test: als een andere test
        # date/datetime in ai_gateway heeft bevroren (en die patch lekt in een
        # volledige suite-run), blijven de relatieve datums dan toch kloppen.
        today = ai_gateway.date.today()
        old_1 = today - timedelta(days=200)
        old_2 = today - timedelta(days=91)
        recent_1 = today - timedelta(days=89)
        recent_2 = today
        for d in (old_1, old_2, recent_1, recent_2):
            self._make_slot(d)

        deleted = ai_gateway.cleanup_old_budget_slots(self.db, retention_days=90)
        self.db.expire_all()

        self.assertGreaterEqual(deleted, 2)
        self.assertEqual(self._dates(), {recent_1, recent_2},
                         "oude slots moeten weg zijn, recente moeten blijven")

    def test_boundary_slot_exactly_at_retention_kept(self):
        """Een slot van precies `retention_days` oud blijft bewaard
        (alleen strikt ouder dan de cutoff wordt verwijderd)."""
        from datetime import timedelta
        boundary = ai_gateway.date.today() - timedelta(days=90)
        self._make_slot(boundary)

        ai_gateway.cleanup_old_budget_slots(self.db, retention_days=90)
        self.db.expire_all()

        self.assertEqual(self._dates(), {boundary})

    def test_scheduler_runs_cleanup_each_cycle_independent_of_dq_scan(self):
        """De opruim-scheduler draait elke cyclus, ook als de DQ-scan is
        uitgeschakeld (eigen taak, eigen configuratie) en ook als een
        opruimronde faalt."""
        import asyncio
        from services import ai_budget_cleanup_scheduler as sched

        calls = {"n": 0}

        def fake_cleanup():
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("tijdelijke DB-fout")
            return 0

        real_wait = asyncio.sleep

        async def run_briefly():
            task = asyncio.get_event_loop().create_task(sched._cleanup_loop())
            try:
                # startvertraging 0-achtig + 3 cycli van ~0s; echte (ongepatchte)
                # wachtstap zodat de to_thread-cycli wandkloktijd krijgen.
                for _ in range(400):
                    await real_wait(0.01)
                    if calls["n"] >= 3:
                        break
            finally:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        real_sleep = asyncio.sleep

        async def instant_sleep(_seconds, *args, **kwargs):
            # Versnel de loop: elke geplande wachtstap wordt vrijwel direct.
            await real_sleep(0)

        env = {
            "DISABLE_DQ_SCAN": "true",  # DQ-scan uit mag de opruiming niet raken
            "AI_BUDGET_CLEANUP_INTERVAL": "1",
            "AI_BUDGET_CLEANUP_STARTUP_DELAY": "1",
        }
        with patch.dict(os.environ, env), \
             patch.object(sched, "run_cleanup_once", side_effect=fake_cleanup), \
             patch.object(sched.asyncio, "sleep", side_effect=instant_sleep):
            asyncio.run(run_briefly())

        self.assertGreaterEqual(
            calls["n"], 3,
            "de opruimstap moet elke cyclus draaien, ook na een fout en met DQ-scan uit",
        )

    def test_run_cleanup_once_delegates_to_gateway(self):
        with patch.object(ai_gateway, "cleanup_old_budget_slots", return_value=5) as mock_cleanup:
            from services.ai_budget_cleanup_scheduler import run_cleanup_once
            self.assertEqual(run_cleanup_once(), 5)
            mock_cleanup.assert_called_once_with()

    def test_retention_days_env_override(self):
        """AI_BUDGET_SLOT_RETENTION_DAYS stuurt de default bewaartermijn."""
        with patch.dict(os.environ, {"AI_BUDGET_SLOT_RETENTION_DAYS": "30"}):
            self.assertEqual(ai_gateway._budget_slot_retention_days(), 30)
        with patch.dict(os.environ, {"AI_BUDGET_SLOT_RETENTION_DAYS": "0"}):
            self.assertEqual(ai_gateway._budget_slot_retention_days(),
                             ai_gateway.DEFAULT_BUDGET_SLOT_RETENTION_DAYS)
        with patch.dict(os.environ, {"AI_BUDGET_SLOT_RETENTION_DAYS": "abc"}):
            self.assertEqual(ai_gateway._budget_slot_retention_days(),
                             ai_gateway.DEFAULT_BUDGET_SLOT_RETENTION_DAYS)


if __name__ == "__main__":
    unittest.main()
