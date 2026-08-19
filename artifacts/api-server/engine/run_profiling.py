"""
Trage-run-bewaking voor nachtelijke engine-orchestraties.

Herbruikbare helper (referentie-implementatie: competition_intelligence.run_all):
- RunProfiler: per-stap wandkloktijd meten + loggen
- check_slow_run: publiceert een engine_slow_run-IntelligenceSignal via
  publish_signal wanneer de totale looptijd van een VOLLEDIGE run boven de
  (per model-governance configureerbare) drempel komt.

Shop-gescopeerde runs (tests, handmatige deel-runs) horen door de aanroepende
engine te worden uitgezonderd: roep check_slow_run dan simpelweg niet aan.

De helper commit NIET zelf; de aanroepende engine-run beheert de transactie.
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Callable, Optional

from sqlalchemy.orm import Session

from engine.signal_publisher import publish_signal

logger = logging.getLogger(__name__)

# Default-drempel (seconden) voor engines die nog geen eigen waarde in hun
# governance-config hebben vastgelegd.
DEFAULT_SLOW_RUN_THRESHOLD_SECONDS = 60.0


class RunProfiler:
    """Meet per-stap wandkloktijd van een engine-run en logt elke stap."""

    def __init__(self, engine_label: str, log: Optional[logging.Logger] = None):
        self.engine_label = engine_label
        self.timings: dict[str, float] = {}
        self._log = log or logger
        self._start = time.monotonic()

    def timed(self, step: str, fn: Callable):
        t0 = time.monotonic()
        out = fn()
        self.timings[step] = round(time.monotonic() - t0, 3)
        self._log.info("%s stap '%s' duurde %.3fs",
                       self.engine_label, step, self.timings[step])
        return out

    def total_seconds(self) -> float:
        # Microseconde-resolutie: bij (in tests) weggemockte stappen mag de
        # totaaltijd niet naar exact 0.0 afronden, anders is een minieme
        # drempel nooit overschrijdbaar.
        return round(time.monotonic() - self._start, 6)


def check_slow_run(
    db: Session,
    profiler: RunProfiler,
    *,
    engine: str,
    entity_name: str,
    run_date: Optional[date] = None,
    threshold_seconds: float,
    model_version: Optional[str] = None,
    total_seconds: Optional[float] = None,
    shop_id: Optional[int] = None,
    entity_id: str = "all",
) -> bool:
    """Publiceer een engine_slow_run-signaal als de run boven de drempel zat.

    Returns True als er een signaal is gepubliceerd (caller commit zelf).
    Een drempel <= 0 schakelt de bewaking uit.
    """
    rd = run_date or date.today()
    total = total_seconds if total_seconds is not None else profiler.total_seconds()
    timings = profiler.timings
    threshold = float(threshold_seconds)
    logger.info("%s run duurde %.3fs totaal (timings: %s)",
                profiler.engine_label, total, timings)
    if threshold <= 0 or total <= threshold:
        return False

    slowest = max(timings, key=timings.get) if timings else None
    publish_signal(
        db, engine=engine, signal_type="engine_slow_run",
        entity_type="shop", entity_id=entity_id, shop_id=shop_id,
        entity_name=entity_name,
        severity="medium", direction="negative",
        metric="engine_run_seconds",
        current_value=total, expected_value=threshold,
        confidence=1.0,
        explanation=(
            f"De volledige {profiler.engine_label}-run van {rd} duurde "
            f"{total:.1f}s; dat overschrijdt de drempel van {threshold:.0f}s. "
            f"Langzaamste stap: {slowest} ({timings.get(slowest, 0):.1f}s)."
            if slowest else
            f"De volledige {profiler.engine_label}-run van {rd} duurde "
            f"{total:.1f}s; dat overschrijdt de drempel van {threshold:.0f}s."),
        evidence={
            "run_date": str(rd),
            "total_seconds": total,
            "threshold_seconds": threshold,
            "timings_seconds": timings,
            "slowest_step": slowest,
        },
        sources=["engine_run_profiling"],
        suggested_action=(
            "Onderzoek de langzaamste stap; controleer datavolume en "
            "query-plannen voordat de vertraging gebruikers raakt"),
        model_version=model_version,
    )
    return True
