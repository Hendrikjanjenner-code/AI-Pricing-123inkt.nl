"""
Gedeelde testconfiguratie: schakel alle achtergrond-schedulers uit tijdens
testruns. Een volledige suite-run duurt langer dan de opstartvertragingen van
de schedulers (feed-sync, DQ-scan, AI-budgetopruiming, AI-sleutelmonitor);
zonder deze vlaggen gaan die taken middenin de run draaien en muteren ze
dezelfde tabellen als de tests (StaleDataError, verdwenen testrijen).
De schedulers hebben hun eigen gerichte tests die ze expliciet aanroepen.
"""
import os

os.environ.setdefault("DISABLE_HEALTH_MONITOR", "true")
os.environ.setdefault("DISABLE_FEED_SYNC", "true")
os.environ.setdefault("DISABLE_DQ_SCAN", "true")
# Let op: de in-app scheduler in main.py leest DISABLE_DATA_QUALITY_SCAN
# (de losse scan-scheduler leest DISABLE_DQ_SCAN); zet beide, anders start
# de scan na de 90s-aanloop alsnog middenin een volledige suite-run.
os.environ.setdefault("DISABLE_DATA_QUALITY_SCAN", "true")
os.environ.setdefault("DISABLE_AI_BUDGET_CLEANUP", "true")
os.environ.setdefault("DISABLE_AI_KEY_MONITOR", "true")
os.environ.setdefault("DISABLE_SCRAPE_SCHEDULER", "true")
# Voorkom dat seed_hierarchy_from_excel() tijdens TestClient(app)-startups
# de hiërarchietabellen muteert. Hiërarchieboom-tests (bijv. test_hierarchy_
# autobuild.py) deactiveren tijdelijk handmatige nodes; een startup-import
# in die toestand zou de boomtoestand vernielen die de test vereist.
os.environ.setdefault("DISABLE_HIERARCHY_SEED", "true")


# ── Cross-run serialisatie van hiërarchie-mutatie-modules ────────────────────
# Validatie- en code-review-runs draaien de volledige suite soms gelijktijdig
# tegen dezelfde gedeelde dev-DB. Modules die de producthiërarchie globaal
# muteren (autobuild/retire, import-apply, deactivate_missing) of er direct
# van afhangen, serialiseren we met een sessie-gebonden Postgres advisory
# lock zodat parallelle runs elkaars boomtoestand niet vernielen.
import pytest as _pytest

HIERARCHY_SUITE_LOCK_KEY = 774411277


@_pytest.fixture(scope="module")
def hierarchy_suite_lock():
    from sqlalchemy import text as _text
    from database import engine as _engine
    conn = _engine.connect()
    if conn.dialect.name != "postgresql":
        yield
        conn.close()
        return
    conn.execute(_text("SELECT pg_advisory_lock(:k)"),
                 {"k": HIERARCHY_SUITE_LOCK_KEY})
    try:
        yield
    finally:
        try:
            conn.execute(_text("SELECT pg_advisory_unlock(:k)"),
                         {"k": HIERARCHY_SUITE_LOCK_KEY})
        finally:
            conn.close()
