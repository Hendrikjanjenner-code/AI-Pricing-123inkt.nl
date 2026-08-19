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
os.environ.setdefault("DISABLE_AI_BUDGET_CLEANUP", "true")
os.environ.setdefault("DISABLE_AI_KEY_MONITOR", "true")
os.environ.setdefault("DISABLE_SCRAPE_SCHEDULER", "true")
