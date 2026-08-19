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
