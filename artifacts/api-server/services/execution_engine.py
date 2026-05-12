"""
Price Execution Engine — Module 4
Voert goedgekeurde prijsadviezen uit zonder externe systemen.
Prijswijzigingen vereisen altijd approval — geen automatische live-zetting.
"""
import csv
import io
import os
from datetime import datetime
from typing import Optional

# ── Execution modes ──────────────────────────────────────────────────────────
MANUAL_EXPORT = "MANUAL_EXPORT"
API_PUSH_READY = "API_PUSH_READY"
DRY_RUN = "DRY_RUN"
BLOCKED_BY_GUARDRAIL = "BLOCKED_BY_GUARDRAIL"

# ── Safety drempelwaarden ────────────────────────────────────────────────────
MAX_CHANGE_PCT_PER_DAY = 0.05   # max 5% per dag
MIN_CONFIDENCE = 0.40           # minimale confidence voor uitvoering
COST_MARGIN_FLOOR = 1.01        # minimaal 1% boven kostprijs


class SafetyViolation(Exception):
    pass


def _apply_safety_rules(line: dict) -> tuple[bool, str]:
    """
    Controleer of een prijsadvies de safety rules doorstaat.
    Geeft (ok, reden) terug.
    """
    sku_id = line.get("sku_id", "?")
    new_price = line.get("new_price")
    old_price = line.get("old_price")
    cost_price = line.get("cost_price")
    min_price = line.get("min_price")
    max_price = line.get("max_price")
    confidence = line.get("confidence_score", 1.0)

    if new_price is None or old_price is None:
        return False, f"{sku_id}: ontbrekende prijs"

    # Confidence te laag
    if confidence < MIN_CONFIDENCE:
        return False, f"{sku_id}: confidence {confidence:.2f} < {MIN_CONFIDENCE}"

    # Onder kostprijs
    if cost_price and new_price < cost_price * COST_MARGIN_FLOOR:
        return False, f"{sku_id}: nieuwe prijs €{new_price:.2f} onder kostprijs × 1.01"

    # Onder min_price
    if min_price and new_price < min_price:
        return False, f"{sku_id}: nieuwe prijs €{new_price:.2f} onder min_price €{min_price:.2f}"

    # Boven max_price
    if max_price and new_price > max_price:
        return False, f"{sku_id}: nieuwe prijs €{new_price:.2f} boven max_price €{max_price:.2f}"

    # Max dagelijkse wijziging
    change_pct = abs(new_price - old_price) / old_price
    if change_pct > MAX_CHANGE_PCT_PER_DAY:
        return False, f"{sku_id}: wijziging {change_pct*100:.1f}% overschrijdt daggrens van {MAX_CHANGE_PCT_PER_DAY*100:.0f}%"

    return True, "ok"


class PriceExecutionConnector:
    """Generieke interface voor prijsuitvoering naar een extern systeem."""

    def validate_payload(self, lines: list[dict]) -> list[dict]:
        """Valideer payload en retourneer lijst met eventuele fouten."""
        fouten = []
        for line in lines:
            ok, reden = _apply_safety_rules(line)
            if not ok:
                fouten.append({"sku_id": line.get("sku_id"), "fout": reden})
        return fouten

    def push_prices(self, lines: list[dict]) -> dict:
        """Stuur prijzen door naar extern systeem (stub)."""
        raise NotImplementedError("Implementeer in subklasse")

    def rollback_prices(self, job_id: int, db) -> dict:
        """Draai uitvoering terug naar originele prijzen."""
        raise NotImplementedError("Implementeer in subklasse")

    def get_execution_status(self, job_id: int, db) -> dict:
        """Haal uitvoeringsstatus op."""
        raise NotImplementedError("Implementeer in subklasse")


class DemoCommerceConnector(PriceExecutionConnector):
    """
    Demo-connector — simuleert API-push zonder echte externe API.
    Structuur is klaar voor echte integratie.
    """

    def push_prices(self, lines: list[dict]) -> dict:
        """Simuleer het doorsturen van prijzen."""
        geslaagd = []
        mislukt = []
        for line in lines:
            ok, reden = _apply_safety_rules(line)
            if ok:
                geslaagd.append(line["sku_id"])
            else:
                mislukt.append({"sku_id": line["sku_id"], "reden": reden})
        return {
            "status": "gesimuleerd",
            "geslaagd": len(geslaagd),
            "mislukt": len(mislukt),
            "details": mislukt,
        }

    def rollback_prices(self, job_id: int, db) -> dict:
        """Draai een job terug via rollback_price velden."""
        from models import PriceExecutionLine
        lines = db.query(PriceExecutionLine).filter(PriceExecutionLine.job_id == job_id).all()
        teruggezet = 0
        for line in lines:
            if line.rollback_price is not None:
                line.status = "teruggedraaid"
                teruggezet += 1
        db.commit()
        return {"job_id": job_id, "teruggezet": teruggezet, "status": "teruggedraaid"}

    def get_execution_status(self, job_id: int, db) -> dict:
        from models import PriceExecutionJob
        job = db.query(PriceExecutionJob).filter(PriceExecutionJob.job_id == job_id).first()
        if not job:
            return {"fout": "Job niet gevonden"}
        return {
            "job_id": job.job_id,
            "status": job.status,
            "execution_mode": job.execution_mode,
            "approved_count": job.approved_count,
            "rejected_count": job.rejected_count,
            "created_at": str(job.created_at),
        }


def create_execution_job(
    db,
    lines: list[dict],
    created_by: str,
    execution_mode: str = MANUAL_EXPORT,
) -> dict:
    """
    Maak een uitvoering-batch aan na safety-controle.
    Stap 1–4 van de execution flow.
    Geeft job-info + gevalideerde regels terug.
    """
    from models import PriceExecutionJob, PriceExecutionLine

    connector = DemoCommerceConnector()
    fouten = connector.validate_payload(lines)
    fout_skus = {f["sku_id"] for f in fouten}

    goedgekeurd = [l for l in lines if l.get("sku_id") not in fout_skus]
    afgewezen = [l for l in lines if l.get("sku_id") in fout_skus]

    # Blokkeer als er safety violations zijn en mode niet DRY_RUN
    effectieve_mode = execution_mode
    if afgewezen and execution_mode not in (DRY_RUN,):
        effectieve_mode = BLOCKED_BY_GUARDRAIL if not goedgekeurd else execution_mode

    job = PriceExecutionJob(
        created_by=created_by,
        execution_mode=effectieve_mode,
        status="aangemaakt",
        approved_count=len(goedgekeurd),
        rejected_count=len(afgewezen),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    for l in goedgekeurd + afgewezen:
        change_pct = None
        if l.get("old_price") and l.get("new_price"):
            change_pct = round((l["new_price"] - l["old_price"]) / l["old_price"] * 100, 2)
        db_line = PriceExecutionLine(
            job_id=job.job_id,
            sku_id=l["sku_id"],
            old_price=l.get("old_price"),
            new_price=l.get("new_price"),
            change_pct=change_pct,
            status="goedgekeurd" if l["sku_id"] not in fout_skus else "afgewezen_guardrail",
            reason_code=l.get("reason_code"),
            rollback_price=l.get("old_price"),
        )
        db.add(db_line)
    db.commit()

    return {
        "job_id": job.job_id,
        "execution_mode": effectieve_mode,
        "status": job.status,
        "approved_count": job.approved_count,
        "rejected_count": job.rejected_count,
        "safety_violations": fouten,
    }


def generate_export_csv(lines: list[dict]) -> str:
    """
    Genereer een CSV-exportbestand voor prijswijzigingen (stap 5).
    Geeft CSV-inhoud als string terug.
    """
    output = io.StringIO()
    velden = [
        "sku_id", "old_price", "new_price", "change_pct",
        "min_price", "max_price", "reason_code", "confidence_score",
        "approved_by", "approved_at", "execution_status",
    ]
    writer = csv.DictWriter(output, fieldnames=velden, extrasaction="ignore")
    writer.writeheader()
    for line in lines:
        writer.writerow({k: line.get(k, "") for k in velden})
    return output.getvalue()
