"""
Voer alle backfill-scripts in de juiste volgorde uit.

Gebruik:
    python artifacts/api-server/backfill_all.py

Elke stap is idempotent — al gevulde tabellen worden overgeslagen.
Elk script wordt als apart subproces uitgevoerd zodat sys.exit()-aanroepen
in individuele scripts de sequentie niet onderbreken.

Volgorde (op basis van data-afhankelijkheden):
  1. backfill_new_tables        — competition scores, A/B tests, CIS, elasticiteit, ISV
  2. backfill_category_hierarchy — categorieënhiërarchie (vereist dim_product)
  3. backfill_bcg               — BCG-classificaties (vereist dim_product)
  4. backfill_traffic           — traffic & zoekvolume
  5. backfill_intelligence      — kosten, marketing, OCS, inkoop, economie, BCG-transities
  6. backfill_break_even        — kostprijswijziging & break-even (PPFS leest BCG-data)
  7. backfill_ecosystem         — traffic driver & mandjeintelligentie
"""
import subprocess
import sys
import os
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

STEPS = [
    ("backfill_new_tables",         "Competition scores, A/B tests, CIS, elasticiteit, ISV"),
    ("backfill_category_hierarchy", "Categorieënhiërarchie"),
    ("backfill_bcg",                "BCG-classificaties"),
    ("backfill_traffic",            "Traffic & zoekvolume"),
    ("backfill_intelligence",       "Kosten, marketing, OCS, inkoop, economie, BCG-transities"),
    ("backfill_break_even",         "Kostprijswijziging & break-even analyse"),
    ("backfill_ecosystem",          "Traffic driver & mandjeintelligentie"),
    ("backfill_competition_engine", "Competition Intelligence Engine 2.0 — profielen, categoryscores, strategieën"),
]


def run_step(script_name: str, description: str, step_num: int, total: int) -> bool:
    """Voer één backfill-script uit als subproces. Geeft True terug bij succes."""
    script_path = os.path.join(SCRIPT_DIR, f"{script_name}.py")

    print(f"\n{'─' * 60}")
    print(f"Stap {step_num}/{total}: {description}")
    print(f"Script: {script_name}.py")
    print(f"{'─' * 60}")

    if not os.path.exists(script_path):
        print(f"⚠️  Script niet gevonden: {script_path} — overgeslagen")
        return True

    start = time.time()
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=SCRIPT_DIR,
        capture_output=False,
    )
    elapsed = time.time() - start

    if result.returncode == 0:
        print(f"✅ Stap {step_num} voltooid in {elapsed:.1f}s")
        return True
    else:
        print(f"❌ Stap {step_num} mislukt (exitcode {result.returncode}) na {elapsed:.1f}s")
        return False


def main() -> int:
    total = len(STEPS)
    failed: list[str] = []

    print("=" * 60)
    print("  Backfill All — AI Pricing Decision Engine")
    print(f"  {total} stappen, alle stappen zijn idempotent")
    print("=" * 60)

    overall_start = time.time()

    for i, (script_name, description) in enumerate(STEPS, start=1):
        success = run_step(script_name, description, i, total)
        if not success:
            failed.append(script_name)

    overall_elapsed = time.time() - overall_start

    print(f"\n{'=' * 60}")
    if not failed:
        print(f"✅ Alle {total} stappen succesvol afgerond in {overall_elapsed:.1f}s")
        return 0
    else:
        print(f"⚠️  {len(failed)} stap(pen) mislukt: {', '.join(failed)}")
        print("Controleer de uitvoer hierboven voor details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
