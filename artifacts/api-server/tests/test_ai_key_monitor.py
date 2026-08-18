"""
AI-sleutel bereikbaarheidsmonitor — gerichte tests voor:
  - probe_provider() gedrag (bereikbaar / onbereikbaar / geen sleutel)
  - TTL-caching: geen herhaalde netwerkoproep binnen het cachevenster
  - force=True: altijd een verse probe
  - Transitie-detectie en alert-aanmaak (_run_probe_cycle)
  - Herstel: open alert wordt gesloten bij reachable=True
  - Startup-state bevat ai_provider_reachable / ai_provider_error velden
"""
import os
import sys
import time
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DISABLE_SCRAPE_SCHEDULER", "true")

import ai_gateway  # noqa: E402


# ─── Helperfuncties ───────────────────────────────────────────────────────────

_P = ai_gateway.PROVIDER_OPENAI  # standaard testprovider


def _reset_probe_cache(reachable=None, error=None, checked_at=0.0, provider=_P):
    """Zet de module-level probe-cache terug naar een bekende staat.

    reachable=None → cache volledig leeg (nog niet getest).
    """
    ai_gateway._probe_cache.clear()
    if reachable is not None:
        ai_gateway._probe_cache[provider] = {
            "reachable": reachable, "error": error, "checked_at": checked_at,
        }


def _patch_active(provider=_P):
    """Patch de actieve provider (DB-instelling) naar een vaste waarde."""
    return patch.object(ai_gateway, "resolve_active_provider", return_value=provider)


def _make_openai_client_mock(fail_with=None):
    """Bouw een OpenAI-clientmock; fail_with=Exception gooit die bij models.list()."""
    client = MagicMock()
    if fail_with:
        client.models.list.side_effect = fail_with
    else:
        client.models.list.return_value = []
    return client


# ─── Tests voor probe_provider() ─────────────────────────────────────────────

class TestProbeProvider(unittest.TestCase):
    def setUp(self):
        _reset_probe_cache()

    def test_returns_false_when_no_provider_configured(self):
        """Zonder geconfigureerde sleutel is de provider onbereikbaar."""
        with patch.object(ai_gateway, "resolve_active_provider", return_value=None):
            reachable, error = ai_gateway.probe_provider(force=True)
        self.assertFalse(reachable)
        self.assertIn("Geen AI-provider", error)

    def test_returns_false_when_chosen_provider_not_configured(self):
        """Expliciet gekozen maar niet geconfigureerde provider → onbereikbaar, geen terugval."""
        with _patch_active(), patch.object(ai_gateway, "_env_config", return_value=None):
            reachable, error = ai_gateway.probe_provider(force=True)
        self.assertFalse(reachable)
        self.assertIn("niet geconfigureerd", error)

    def test_returns_true_when_models_list_succeeds(self):
        """Als models.list() slaagt, is de provider bereikbaar."""
        fake_cfg = {"base_url": None, "api_key": "sk-test", "provider": _P}
        client_mock = _make_openai_client_mock()
        with _patch_active(), \
             patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            reachable, error = ai_gateway.probe_provider(force=True)
        self.assertTrue(reachable)
        self.assertIsNone(error)
        client_mock.models.list.assert_called_once()

    def test_returns_false_when_models_list_raises(self):
        """Als models.list() een uitzondering gooit, is de provider onbereikbaar."""
        fake_cfg = {"base_url": None, "api_key": "sk-bad", "provider": _P}
        client_mock = _make_openai_client_mock(fail_with=Exception("401 Unauthorized"))
        with _patch_active(), \
             patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            reachable, error = ai_gateway.probe_provider(force=True)
        self.assertFalse(reachable)
        self.assertIn("401", error)

    def test_cache_prevents_repeated_network_calls(self):
        """Binnen het cache-venster wordt models.list() niet opnieuw aangeroepen."""
        fake_cfg = {"base_url": None, "api_key": "sk-test", "provider": _P}
        client_mock = _make_openai_client_mock()
        with _patch_active(), \
             patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            # Eerste aanroep vult de cache
            ai_gateway.probe_provider(force=True)
            # Tweede aanroep binnen TTL — moet de cache gebruiken
            ai_gateway.probe_provider(force=False)
        # models.list() mag maar één keer zijn aangeroepen
        self.assertEqual(client_mock.models.list.call_count, 1)

    def test_force_bypasses_cache(self):
        """force=True slaat de cache altijd over."""
        fake_cfg = {"base_url": None, "api_key": "sk-test", "provider": _P}
        client_mock = _make_openai_client_mock()
        with _patch_active(), \
             patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            ai_gateway.probe_provider(force=True)
            ai_gateway.probe_provider(force=True)
        self.assertEqual(client_mock.models.list.call_count, 2)

    def test_expired_cache_triggers_new_probe(self):
        """Als de cache verlopen is (checked_at = 0), wordt een nieuwe probe gedaan."""
        fake_cfg = {"base_url": None, "api_key": "sk-test", "provider": _P}
        client_mock = _make_openai_client_mock()
        # Cache als verlopen markeren
        _reset_probe_cache(reachable=True, error=None, checked_at=0.0)
        with _patch_active(), \
             patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            ai_gateway.probe_provider(force=False)
        self.assertEqual(client_mock.models.list.call_count, 1)

    def test_fresh_cache_skips_network(self):
        """Als de cache vers is, wordt geen netwerkoproep gedaan."""
        fake_cfg = {"base_url": None, "api_key": "sk-test", "provider": _P}
        client_mock = _make_openai_client_mock()
        # Cache als vers markeren
        _reset_probe_cache(reachable=True, error=None, checked_at=time.time())
        with _patch_active(), \
             patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            reachable, _ = ai_gateway.probe_provider(force=False)
        client_mock.models.list.assert_not_called()
        self.assertTrue(reachable)

    def test_probe_cache_is_per_provider(self):
        """Een verse cache voor provider A geldt niet voor provider B."""
        fake_cfg = {"base_url": None, "api_key": "sk-test", "provider": ai_gateway.PROVIDER_REPLIT}
        client_mock = _make_openai_client_mock()
        # Cache vers voor openai_direct; probe replit → moet wel netwerk doen
        _reset_probe_cache(reachable=True, error=None, checked_at=time.time())
        with patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            ai_gateway.probe_provider(force=False, provider=ai_gateway.PROVIDER_REPLIT)
        client_mock.models.list.assert_called_once()

    def test_get_provider_reachable_returns_cached_state(self):
        """get_provider_reachable() geeft de gecachte staat terug zonder netwerkoproep."""
        _reset_probe_cache(reachable=True, error=None, checked_at=time.time())
        with _patch_active():
            reachable, error = ai_gateway.get_provider_reachable()
        self.assertTrue(reachable)
        self.assertIsNone(error)

    def test_get_provider_reachable_returns_none_when_not_probed(self):
        """get_provider_reachable() geeft None terug als er nog geen probe is gedaan."""
        _reset_probe_cache()
        with _patch_active():
            reachable, error = ai_gateway.get_provider_reachable()
        self.assertIsNone(reachable)

    def test_probe_updates_cache(self):
        """Na een succesvolle probe is de cache bijgewerkt met reachable=True."""
        fake_cfg = {"base_url": None, "api_key": "sk-test", "provider": _P}
        client_mock = _make_openai_client_mock()
        _reset_probe_cache()
        with _patch_active(), \
             patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            ai_gateway.probe_provider(force=True)
        self.assertTrue(ai_gateway._probe_cache[_P]["reachable"])
        self.assertGreater(ai_gateway._probe_cache[_P]["checked_at"], 0)

    def test_probe_failure_updates_cache_with_error(self):
        """Na een mislukte probe slaat de cache reachable=False en de foutmelding op."""
        fake_cfg = {"base_url": None, "api_key": "sk-bad", "provider": _P}
        client_mock = _make_openai_client_mock(fail_with=Exception("Connection refused"))
        _reset_probe_cache()
        with _patch_active(), \
             patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            ai_gateway.probe_provider(force=True)
        self.assertFalse(ai_gateway._probe_cache[_P]["reachable"])
        self.assertIn("Connection refused", ai_gateway._probe_cache[_P]["error"])


# ─── Tests voor _run_probe_cycle (transitie-detectie + alerting) ─────────────

class TestRunProbeCycle(unittest.TestCase):
    def setUp(self):
        _reset_probe_cache()

    def test_no_alert_when_state_unchanged_reachable(self):
        """Geen alert als de status gelijk blijft (bereikbaar → bereikbaar)."""
        from services.ai_key_monitor import _run_probe_cycle
        previous = [True]
        with patch.object(ai_gateway, "probe_provider", return_value=(True, None)), \
             patch("services.ai_key_monitor._emit_alert") as mock_alert:
            _run_probe_cycle(previous)
        mock_alert.assert_not_called()

    def test_no_alert_when_state_unchanged_unreachable(self):
        """Geen alert als de status gelijk blijft (onbereikbaar → onbereikbaar)."""
        from services.ai_key_monitor import _run_probe_cycle
        previous = [False]
        with patch.object(ai_gateway, "probe_provider", return_value=(False, "fout")), \
             patch("services.ai_key_monitor._emit_alert") as mock_alert:
            _run_probe_cycle(previous)
        mock_alert.assert_not_called()

    def test_alert_emitted_on_healthy_to_unreachable(self):
        """Alert wordt aangemaakt bij transitie bereikbaar → onbereikbaar."""
        from services.ai_key_monitor import _run_probe_cycle
        previous = [True]
        err = "401 Unauthorized"
        with patch.object(ai_gateway, "probe_provider", return_value=(False, err)), \
             patch("services.ai_key_monitor._emit_alert") as mock_alert:
            _run_probe_cycle(previous)
        mock_alert.assert_called_once_with(False, err)
        self.assertFalse(previous[0])

    def test_recovery_alert_on_unreachable_to_healthy(self):
        """Herstel-alert wordt aangemaakt bij transitie onbereikbaar → bereikbaar."""
        from services.ai_key_monitor import _run_probe_cycle
        previous = [False]
        with patch.object(ai_gateway, "probe_provider", return_value=(True, None)), \
             patch("services.ai_key_monitor._emit_alert") as mock_alert:
            _run_probe_cycle(previous)
        mock_alert.assert_called_once_with(True, None)
        self.assertTrue(previous[0])

    def test_first_cycle_from_none_to_reachable_calls_emit(self):
        """Eerste monitorcyclus (None→bereikbaar) roept _emit_alert aan — idempotent als er geen open alert is."""
        from services.ai_key_monitor import _run_probe_cycle
        previous = [None]
        with patch.object(ai_gateway, "probe_provider", return_value=(True, None)), \
             patch("services.ai_key_monitor._emit_alert") as mock_alert:
            _run_probe_cycle(previous)
        mock_alert.assert_called_once_with(True, None)
        self.assertTrue(previous[0])

    def test_first_cycle_from_none_to_unreachable_calls_emit(self):
        """Eerste monitorcyclus (None→onbereikbaar) roept _emit_alert aan."""
        from services.ai_key_monitor import _run_probe_cycle
        previous = [None]
        with patch.object(ai_gateway, "probe_provider", return_value=(False, "fout")), \
             patch("services.ai_key_monitor._emit_alert") as mock_alert:
            _run_probe_cycle(previous)
        mock_alert.assert_called_once_with(False, "fout")
        self.assertFalse(previous[0])


# ─── Tests voor _emit_alert (BacklogItem aanmaken/sluiten) ───────────────────

class TestEmitAlert(unittest.TestCase):
    def _make_db_mock(self, existing_open=None):
        """Bouw een minimale database-sessie-mock."""
        db = MagicMock()
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.first.return_value = existing_open
        db.query.return_value = query_chain
        return db

    def _make_existing_item(self, status="open"):
        item = MagicMock()
        item.status = status
        item.description = "[ai-key-monitor] bestaande fout"
        item.updated_at = None
        return item

    def test_creates_backlog_item_when_unreachable_and_no_open(self):
        """Een nieuw BacklogItem wordt aangemaakt als er nog geen open alert is."""
        from services.ai_key_monitor import _emit_alert
        db = self._make_db_mock(existing_open=None)
        with patch("database.SessionLocal", return_value=db):
            _emit_alert(False, "401 Unauthorized")
        db.add.assert_called_once()
        item = db.add.call_args[0][0]
        self.assertEqual(item.status, "open")
        self.assertIn("[ai-key-monitor]", item.description)
        self.assertEqual(item.priority, "high")
        self.assertEqual(item.item_type, "bug")
        db.commit.assert_called()

    def test_no_duplicate_alert_when_open_exists(self):
        """Geen tweede BacklogItem als er al een open alert bestaat."""
        from services.ai_key_monitor import _emit_alert
        existing = self._make_existing_item(status="open")
        db = self._make_db_mock(existing_open=existing)
        with patch("database.SessionLocal", return_value=db):
            _emit_alert(False, "opnieuw fout")
        db.add.assert_not_called()

    def test_closes_open_alert_on_recovery(self):
        """Een open alert wordt gesloten (status='done') als de provider hersteld is."""
        from services.ai_key_monitor import _emit_alert
        existing = self._make_existing_item(status="open")
        db = self._make_db_mock(existing_open=existing)
        with patch("database.SessionLocal", return_value=db):
            _emit_alert(True, None)
        self.assertEqual(existing.status, "done")
        self.assertIsNotNone(existing.updated_at)
        db.commit.assert_called()

    def test_no_action_on_recovery_with_no_open_alert(self):
        """Geen actie bij herstel als er geen open alert was."""
        from services.ai_key_monitor import _emit_alert
        db = self._make_db_mock(existing_open=None)
        with patch("database.SessionLocal", return_value=db):
            _emit_alert(True, None)
        db.add.assert_not_called()
        db.commit.assert_not_called()


# ─── Tests voor startup_state-velden ─────────────────────────────────────────

class TestStartupState(unittest.TestCase):
    def test_startup_state_has_ai_fields(self):
        """startup_state bevat ai_provider_reachable en ai_provider_error."""
        import main
        self.assertIn("ai_provider_reachable", main.startup_state)
        self.assertIn("ai_provider_error", main.startup_state)

    def test_startup_probe_populates_cache_on_success(self):
        """Na een gesimuleerde succesvolle probe is de cache op True gezet."""
        fake_cfg = {"base_url": None, "api_key": "sk-test", "provider": _P}
        client_mock = _make_openai_client_mock()
        _reset_probe_cache()
        with _patch_active(), \
             patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            reachable, error = ai_gateway.probe_provider(force=True)
        self.assertTrue(reachable)
        self.assertIsNone(error)
        self.assertTrue(ai_gateway._probe_cache[_P]["reachable"])

    def test_startup_probe_populates_cache_on_failure(self):
        """Na een mislukte probe staat de cache op False met foutmelding."""
        fake_cfg = {"base_url": None, "api_key": "sk-bad", "provider": _P}
        client_mock = _make_openai_client_mock(fail_with=Exception("403 Forbidden"))
        _reset_probe_cache()
        with _patch_active(), \
             patch.object(ai_gateway, "_env_config", return_value=fake_cfg), \
             patch("openai.OpenAI", return_value=client_mock):
            reachable, error = ai_gateway.probe_provider(force=True)
        self.assertFalse(reachable)
        self.assertIn("403", error)
        self.assertFalse(ai_gateway._probe_cache[_P]["reachable"])


# ─── Lifecycle-integratie: startup met ongeldige sleutel ─────────────────────

class TestStartupInvalidKeyLifecycle(unittest.TestCase):
    """Simuleert het volledige scenario: ongeldige sleutel bij opstarten.

    Verwacht gedrag:
      1. Startup-probe mislukt → _emit_alert(False, ...) direct vanuit main-startup
      2. Monitor initialiseert altijd op previous=None
      3. Eerste monitorcyclus: None→False → _emit_alert(False, ...) opnieuw — idempotent (geen duplicaat)
      4. Herstel: monitor detecteert None/False→True → _emit_alert(True) sluit het alert
    """

    def _make_db_mock(self, existing_open=None):
        db = MagicMock()
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.first.return_value = existing_open
        db.query.return_value = query_chain
        return db

    def test_startup_failure_creates_immediate_alert(self):
        """Een mislukte startup-probe maakt direct een BacklogItem-alert aan."""
        from services.ai_key_monitor import _emit_alert
        db = self._make_db_mock(existing_open=None)
        with patch("database.SessionLocal", return_value=db):
            _emit_alert(False, "401 Unauthorized — ongeldige sleutel")
        db.add.assert_called_once()
        item = db.add.call_args[0][0]
        self.assertEqual(item.status, "open")
        self.assertIn("[ai-key-monitor]", item.description)
        self.assertIn("401", item.description)
        db.commit.assert_called()

    def test_first_monitor_cycle_does_not_duplicate_existing_alert(self):
        """De eerste monitorcyclus (None→False) maakt geen duplicaat als er al een open alert is."""
        from services.ai_key_monitor import _emit_alert
        existing = MagicMock()
        existing.status = "open"
        existing.description = "[ai-key-monitor] eerder aangemaakt"
        db = self._make_db_mock(existing_open=existing)
        with patch("database.SessionLocal", return_value=db):
            _emit_alert(False, "401 Unauthorized")
        db.add.assert_not_called()

    def test_recovery_closes_startup_alert(self):
        """Wanneer de sleutel hersteld is, sluit _emit_alert(True) het startup-alert."""
        from services.ai_key_monitor import _emit_alert
        existing = MagicMock()
        existing.status = "open"
        existing.description = "[ai-key-monitor] startup-alert"
        existing.updated_at = None
        db = self._make_db_mock(existing_open=existing)
        with patch("database.SessionLocal", return_value=db):
            _emit_alert(True, None)
        self.assertEqual(existing.status, "done")
        db.commit.assert_called()

    def test_full_lifecycle_invalid_then_recovered(self):
        """Volledig lifecycle: startup-fout → open alert → herstel → alert gesloten."""
        from services.ai_key_monitor import _run_probe_cycle, _emit_alert

        # Fase 1: startup-probe mislukt → direct alert aanmaken
        db_fail = self._make_db_mock(existing_open=None)
        with patch("database.SessionLocal", return_value=db_fail):
            _emit_alert(False, "verbinding geweigerd")
        db_fail.add.assert_called_once()
        startup_item = db_fail.add.call_args[0][0]
        self.assertEqual(startup_item.status, "open")

        # Fase 2: eerste monitorcyclus (None→False) — geen duplicaat
        # previous=None omdat monitor altijd op None initialiseert
        previous = [None]
        existing_open = MagicMock()
        existing_open.status = "open"
        existing_open.description = "[ai-key-monitor] startup"
        db_cycle1 = self._make_db_mock(existing_open=existing_open)
        with patch.object(ai_gateway, "probe_provider", return_value=(False, "verbinding geweigerd")), \
             patch("database.SessionLocal", return_value=db_cycle1):
            _run_probe_cycle(previous)
        db_cycle1.add.assert_not_called()  # geen duplicaat
        self.assertFalse(previous[0])

        # Fase 3: sleutel hersteld → alert wordt gesloten
        existing_open2 = MagicMock()
        existing_open2.status = "open"
        existing_open2.description = "[ai-key-monitor] startup"
        existing_open2.updated_at = None
        db_cycle2 = self._make_db_mock(existing_open=existing_open2)
        with patch.object(ai_gateway, "probe_provider", return_value=(True, None)), \
             patch("database.SessionLocal", return_value=db_cycle2):
            _run_probe_cycle(previous)
        self.assertEqual(existing_open2.status, "done")
        db_cycle2.commit.assert_called()
        self.assertTrue(previous[0])

    def test_monitor_initializes_previous_as_none(self):
        """De monitor initialiseert previous_reachable altijd op None (niet vanuit cache)."""
        # Zet de cache als "bereikbaar" — de monitor mag dit NIET gebruiken
        _reset_probe_cache(reachable=True, error=None, checked_at=time.time())
        from services import ai_key_monitor
        # _monitor_loop gebruikt [None] als startwaarde, ongeacht de cache-inhoud.
        # Verifieer dit door _run_probe_cycle te tracen met previous=[None].
        previous = [None]
        with patch.object(ai_gateway, "probe_provider", return_value=(True, None)), \
             patch("services.ai_key_monitor._emit_alert") as mock_alert:
            ai_key_monitor._run_probe_cycle(previous)
        # Eerste cyclus: None→True → _emit_alert(True) wordt aangeroepen
        mock_alert.assert_called_once_with(True, None)


if __name__ == "__main__":
    unittest.main()
