"""
Symmetrische versleuteling voor connector-credentials.

Leidt een Fernet-sleutel af uit SESSION_SECRET.
SESSION_SECRET is verplicht — ontbreekt het, dan weigert de module te werken.
Wordt uitsluitend gebruikt in routes/connectors.py — geheimen verlaten
de database nooit als plaintext via de API.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any


def _get_fernet():
    """Laad cryptography.fernet.Fernet (optionele dep)."""
    try:
        from cryptography.fernet import Fernet, InvalidToken
        return Fernet, InvalidToken
    except ImportError as exc:
        raise RuntimeError(
            "cryptography-pakket niet geïnstalleerd. "
            "Voer 'pip install cryptography' uit."
        ) from exc


def _derive_key() -> bytes:
    """
    Leid een 32-byte Fernet-sleutel af uit SESSION_SECRET.
    Gooit een RuntimeError als de omgevingsvariabele niet is ingesteld —
    credentials mogen nooit versleuteld worden met een voorspelbare sleutel.
    """
    secret = os.environ.get("SESSION_SECRET", "").strip()
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET is niet ingesteld. "
            "Stel deze omgevingsvariabele in voordat je connector-credentials opslaat. "
            "Connector-credentials kunnen niet worden versleuteld zonder een geheime sleutel."
        )
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_credentials(creds: dict[str, Any]) -> str:
    """Versleutel een dict naar een Fernet-token (base64-string)."""
    Fernet, _ = _get_fernet()
    key = _derive_key()
    f = Fernet(key)
    payload = json.dumps(creds).encode()
    return f.encrypt(payload).decode()


def decrypt_credentials(token: str) -> dict[str, Any]:
    """Ontsleutel een Fernet-token naar de originele dict."""
    Fernet, InvalidToken = _get_fernet()
    key = _derive_key()
    f = Fernet(key)
    try:
        payload = f.decrypt(token.encode())
        return json.loads(payload)
    except (InvalidToken, Exception) as exc:
        raise ValueError(f"Credential-decryptie mislukt: {exc}") from exc
