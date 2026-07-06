"""
Gedeelde netwerk-/SSRF-hulpfuncties voor connectors.

Eén bron van waarheid voor het blokkeren van Server-Side Request Forgery:
gebruikt door zowel routes/connectors.py (verbindingstests) als de
connector-modules zelf (feed-ophaling, health-checks).
"""
from __future__ import annotations

import ipaddress
import socket
from contextlib import contextmanager
from typing import Iterator
from urllib.parse import urljoin, urlparse

import httpx


class UnsafeURLError(ValueError):
    """Opgegeven URL verwijst naar een privaat/loopback-adres of is ongeldig."""


_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_blocked(addr: ipaddress._BaseAddress) -> bool:
    """
    Blokkeer alles wat niet publiek routeerbaar is. Gebruikt een allowlist-
    benadering (`is_global`) zodat óók 0.0.0.0/::, gereserveerde en multicast-
    adressen worden geweigerd. IPv4-mapped IPv6 (bv. ::ffff:127.0.0.1) wordt
    eerst genormaliseerd, anders zou de mapping de controle omzeilen.
    """
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        addr = mapped
    if not addr.is_global:
        return True
    # Extra vangnet naast is_global (defence-in-depth).
    return any(addr in net for net in _PRIVATE_NETWORKS)


def validate_external_url(url: str) -> None:
    """
    Blokkeer SSRF door te controleren of de URL naar een extern,
    niet-privaat adres verwijst. Gooit UnsafeURLError als de URL verdacht is.

    Belangrijk: UnsafeURLError is een subklasse van ValueError, dus het
    parsen van IP-adressen (dat ValueError kan gooien) wordt strikt gescheiden
    gehouden van het gooien van UnsafeURLError — anders zou een `except
    ValueError` de blokkade stilzwijgend inslikken.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise UnsafeURLError("Ongeldige URL.")

    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("Alleen http:// en https:// zijn toegestaan.")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("URL bevat geen geldige hostnaam.")

    # Verzamel de te controleren IP-adressen (zonder UnsafeURLError te gooien).
    candidates: list[ipaddress._BaseAddress] = []
    try:
        candidates.append(ipaddress.ip_address(hostname))
    except ValueError:
        # Hostnaam is een domeinnaam — los op en controleer alle resultaten.
        try:
            resolved = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            # Niet oplosbaar — doorlaten (echte fout wordt bij http-aanroep afgevangen)
            return
        for _fam, _type, _proto, _canon, sockaddr in resolved:
            try:
                candidates.append(ipaddress.ip_address(sockaddr[0]))
            except ValueError:
                pass

    # Blokkeer als één van de kandidaten in een privé/loopback-range valt.
    for addr in candidates:
        if _is_blocked(addr):
            raise UnsafeURLError(
                f"Privé- of loopback-adres niet toegestaan: {addr} "
                f"(hostnaam '{hostname}')."
            )


def safe_get(
    url: str,
    *,
    timeout: float | httpx.Timeout = 30.0,
    max_redirects: int = 5,
) -> httpx.Response:
    """
    Voer een SSRF-veilige GET uit. Automatische redirects zijn UITgeschakeld;
    elke hop (inclusief de eerste URL) wordt opnieuw door validate_external_url
    gehaald voordat het verzoek verstuurd wordt. Zo kan een externe feed niet
    doorverwijzen naar een intern/privaat adres (bv. cloud-metadata).

    Gooit UnsafeURLError als een (redirect-)doel onveilig is en
    httpx.RequestError / httpx.HTTPStatusError bij netwerk-/HTTP-fouten.
    """
    current = url
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            validate_external_url(current)
            resp = client.get(current)
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    return resp
                current = urljoin(current, location)
                continue
            return resp
    raise UnsafeURLError(
        f"Te veel redirects (>{max_redirects}) bij het ophalen van de feed."
    )


@contextmanager
def safe_stream(
    url: str,
    *,
    timeout: float | httpx.Timeout = 30.0,
    max_redirects: int = 5,
) -> Iterator[httpx.Response]:
    """
    SSRF-veilige streaming-GET: identieke redirect-validatie als safe_get, maar
    de response-body wordt NIET vooraf ingelezen. Ideaal voor bereikbaarheids-
    checks op grote feeds — de status/headers zijn beschikbaar zonder de hele
    payload te downloaden. Gebruik als context manager:

        with safe_stream(url) as resp:
            resp.status_code            # beschikbaar
            first = next(resp.iter_bytes(1024), b"")  # optioneel eerste bytes
    """
    current = url
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            validate_external_url(current)
            with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        yield resp
                        return
                    current = urljoin(current, location)
                    continue
                yield resp
                return
    raise UnsafeURLError(
        f"Te veel redirects (>{max_redirects}) bij het ophalen van de feed."
    )
