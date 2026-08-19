"""
Health-notifier — verstuurt waarschuwingen wanneer een databron (connector)
uitvalt.

Ondersteunt twee bezorgkanalen, in deze volgorde:
  1. E-mail via SMTP (als SMTP_HOST is ingesteld)
  2. Webhook via HTTP POST (als ALERT_WEBHOOK_URL is ingesteld)

Als geen van beide is geconfigureerd, wordt de waarschuwing alleen gelogd,
zodat de rest van het systeem nooit crasht door een ontbrekende mailconfig.

Relevante omgevingsvariabelen:
  SMTP_HOST, SMTP_PORT (25), SMTP_USERNAME, SMTP_PASSWORD,
  SMTP_FROM, SMTP_USE_TLS (true)      — SMTP-instellingen
  ALERT_EMAIL_TO                       — komma-gescheiden extra ontvangers
  ALERT_WEBHOOK_URL                    — HTTP-endpoint voor JSON-webhook
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger("uvicorn.error")

# Rollen die als "analisten" een melding moeten ontvangen bij uitval.
ALERT_ROLES = ("analyst", "pricing_manager", "admin")


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def get_alert_recipients(db, roles: tuple[str, ...] = ALERT_ROLES) -> list[str]:
    """
    Verzamel de e-mailadressen van gebruikers met een van de opgegeven rollen
    plus eventuele extra adressen uit ALERT_EMAIL_TO / ALERT_EMAIL. Dubbele
    adressen worden ontdubbeld met behoud van volgorde.
    """
    recipients: list[str] = []

    try:
        import models
        users = (
            db.query(models.User)
            .filter(
                models.User.is_active == True,
                models.User.role.in_(roles),
            )
            .all()
        )
        for u in users:
            if u.email and u.email.strip():
                recipients.append(u.email.strip())
    except Exception as exc:  # noqa: BLE001 — nooit crashen op ontvangers-ophalen
        logger.warning("Kon alert-ontvangers niet ophalen uit DB: %s", exc)

    # ALERT_EMAIL_TO is de primaire variabele; ALERT_EMAIL wordt als alias
    # ondersteund zodat een eenvoudige configuratie ook werkt.
    for env_name in ("ALERT_EMAIL_TO", "ALERT_EMAIL"):
        extra = os.environ.get(env_name, "")
        for addr in extra.split(","):
            addr = addr.strip()
            if addr:
                recipients.append(addr)

    # Ontdubbelen, volgorde behouden
    seen: set[str] = set()
    unique: list[str] = []
    for addr in recipients:
        low = addr.lower()
        if low not in seen:
            seen.add(low)
            unique.append(addr)
    return unique


def _send_email(recipients: list[str], subject: str, body: str) -> bool:
    """Verstuur een e-mail via SMTP. Geeft True bij succes, anders False."""
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return False
    if not recipients:
        logger.warning("SMTP is geconfigureerd maar er zijn geen ontvangers.")
        return False

    port = int(os.environ.get("SMTP_PORT", "25") or "25")
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    sender = os.environ.get("SMTP_FROM", "").strip() or (username or "alerts@pricing.local")
    use_tls = _bool_env("SMTP_USE_TLS", default=True)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if use_tls:
                try:
                    server.starttls()
                except smtplib.SMTPException:
                    logger.warning("SMTP STARTTLS niet ondersteund door %s; ga door zonder TLS.", host)
            if username and password:
                server.login(username, password)
            server.send_message(msg)
        logger.info("Uitval-melding per e-mail verstuurd naar %d ontvanger(s).", len(recipients))
        return True
    except Exception as exc:  # noqa: BLE001 — mailfout mag de monitor niet stoppen
        logger.error("Versturen van uitval-e-mail mislukt: %s", exc)
        return False


def _send_webhook(subject: str, body: str, payload: dict) -> bool:
    """Verstuur een JSON-webhook. Geeft True bij succes, anders False."""
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return False
    try:
        import httpx
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, json={"subject": subject, "text": body, **payload})
            if resp.status_code < 400:
                logger.info("Uitval-melding via webhook verstuurd (HTTP %s).", resp.status_code)
                return True
            logger.error("Webhook-melding gaf HTTP %s terug.", resp.status_code)
            return False
    except Exception as exc:  # noqa: BLE001
        logger.error("Versturen van webhook-melding mislukt: %s", exc)
        return False


def send_connector_alert(
    db,
    *,
    connector_name: str,
    connector_label: str,
    status: str,
    message: str,
    previous_status: Optional[str],
) -> bool:
    """
    Verstuur een uitval-melding voor een connector via e-mail en/of webhook.

    Geeft True als minstens één kanaal de melding heeft afgeleverd, anders
    False (in dat geval is de melding alleen gelogd).
    """
    recipients = get_alert_recipients(db)

    prev = previous_status or "onbekend"
    subject = f"[AI Pricing] Databron '{connector_label}' is uitgevallen ({status})"
    body = (
        f"De databron '{connector_label}' ({connector_name}) is niet langer "
        f"gezond.\n\n"
        f"Nieuwe status : {status}\n"
        f"Vorige status : {prev}\n"
        f"Details       : {message}\n\n"
        f"Deze melding is automatisch gegenereerd door de "
        f"connector-gezondheidsmonitor. Log in op het dashboard om de "
        f"connector te controleren.\n"
    )
    payload = {
        "connector": connector_name,
        "label": connector_label,
        "status": status,
        "previous_status": previous_status,
        "message": message,
    }

    emailed = _send_email(recipients, subject, body)
    hooked = _send_webhook(subject, body, payload)

    if not emailed and not hooked:
        logger.warning(
            "Databron '%s' viel uit (status=%s), maar er is geen "
            "meldingskanaal geconfigureerd (SMTP_HOST / ALERT_WEBHOOK_URL). "
            "Melding: %s",
            connector_label, status, message,
        )
        return False
    return True

def send_ai_key_alert(
    db,
    *,
    reachable: bool,
    error: Optional[str] = None,
) -> bool:
    """
    Verstuur een melding naar beheerders (admins) wanneer de AI-provider
    onbereikbaar wordt (reachable=False) of herstelt (reachable=True).

    Geeft True als minstens één kanaal de melding heeft afgeleverd, anders
    False (in dat geval is de melding alleen gelogd).
    """
    recipients = get_alert_recipients(db, roles=("admin",))

    if reachable:
        subject = "[AI Pricing] AI-provider hersteld — Copilot weer beschikbaar"
        body = (
            "De verbinding met de geconfigureerde LLM-provider is hersteld.\n\n"
            "De Copilot werkt weer normaal; de fail-safe modus is opgeheven.\n\n"
            "Deze melding is automatisch gegenereerd door de AI-sleutel monitor.\n"
        )
    else:
        subject = "[AI Pricing] AI-provider ONBEREIKBAAR — Copilot in fail-safe modus"
        body = (
            "De geconfigureerde LLM-provider is niet bereikbaar.\n\n"
            f"Foutmelding: {error or '(onbekend)'}\n\n"
            "Controleer de OPENAI_API_KEY of AI_INTEGRATIONS_OPENAI_API_KEY/"
            "BASE_URL in de omgevingsvariabelen en vervang de sleutel indien "
            "verlopen of ongeldig. De Copilot geeft zolang een gestructureerd "
            "foutantwoord (fail-safe modus); de rest van de applicatie is niet "
            "beïnvloed.\n\n"
            "Deze melding is automatisch gegenereerd door de AI-sleutel monitor.\n"
        )

    payload = {
        "source": "ai_key_monitor",
        "event": "recovered" if reachable else "down",
        "reachable": reachable,
        "error": error,
    }

    emailed = _send_email(recipients, subject, body)
    hooked = _send_webhook(subject, body, payload)

    if not emailed and not hooked:
        logger.warning(
            "AI-provider statuswijziging (%s), maar er is geen meldingskanaal "
            "geconfigureerd (SMTP_HOST / ALERT_WEBHOOK_URL).",
            "hersteld" if reachable else "onbereikbaar",
        )
        return False
    return True
