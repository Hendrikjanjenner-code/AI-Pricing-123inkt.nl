"""
Metering & observability framework (masterprompt §37-§38, §41-§42).

- record_usage(...): schrijft een CostUsageRecord (gebufferd, batch-flush)
  zodat metering nooit een request vertraagt of laat falen.
- Rolling in-memory metrics per module: response times, error counts —
  gevoed door de request-middleware, gebruikt door het Platform Health Center.
- Error ring buffer: laatste N fouten met correlation ID voor drill-down.

Kostentarieven komen uit platform_assumptions (of defaults hieronder) zodat
de aannames zichtbaar en bewerkbaar zijn (§64.11).
"""
import logging
import threading
import time
from collections import deque
from datetime import datetime

logger = logging.getLogger("uvicorn.error")

# ------------------------------------------------------------------
# Default kostentarieven (EUR). Overschrijfbaar via platform_assumptions.
# ------------------------------------------------------------------
DEFAULT_RATES = {
    "rate_api_request_eur": 0.00002,     # per API-request (compute-aandeel)
    "rate_ai_token_eur": 0.000004,       # per token (in+uit gemiddeld)
    "rate_job_second_eur": 0.0002,       # per seconde jobduur
    "rate_import_row_eur": 0.000005,     # per geïmporteerde rij
    "rate_db_gb_month_eur": 0.35,        # per GB databaseopslag per maand
}

# ------------------------------------------------------------------
# Buffer voor CostUsageRecord-rijen (batch-flush, nooit blocking op request)
# ------------------------------------------------------------------
_buffer: list[dict] = []
_buffer_lock = threading.Lock()
_last_flush = time.monotonic()
FLUSH_MAX_ROWS = 50
FLUSH_MAX_SECONDS = 20


def _rates_from_db(db) -> dict:
    """Lees tarieven uit platform_assumptions; val terug op defaults."""
    from models import PlatformAssumption
    rates = dict(DEFAULT_RATES)
    try:
        for row in db.query(PlatformAssumption).filter(
            PlatformAssumption.key.in_(list(DEFAULT_RATES.keys()))
        ).all():
            rates[row.key] = float(row.value)
    except Exception:
        pass
    return rates


# Cache van tarieven uit platform_assumptions zodat record_usage() de
# bewerkbare aannames gebruikt zonder per record een query te doen.
_rates_cache: dict = {"rates": None, "ts": 0.0}
RATES_CACHE_TTL = 60.0


def current_rates() -> dict:
    """Tarieven uit platform_assumptions (gecachet); fallback op defaults."""
    now = time.monotonic()
    if _rates_cache["rates"] is None or (now - _rates_cache["ts"]) > RATES_CACHE_TTL:
        rates = dict(DEFAULT_RATES)
        try:
            from database import SessionLocal
            db = SessionLocal()
            try:
                rates = _rates_from_db(db)
            finally:
                db.close()
        except Exception:
            pass
        _rates_cache["rates"] = rates
        _rates_cache["ts"] = now
    return _rates_cache["rates"]


def invalidate_rates_cache() -> None:
    _rates_cache["rates"] = None


# ------------------------------------------------------------------
# Actor-context uit het request (username via JWT, shop via header/query)
# ------------------------------------------------------------------
_username_cache: dict = {}  # user_id -> (username, expires_monotonic)
USERNAME_CACHE_TTL = 900.0


def actor_from_request(request) -> tuple:
    """Best-effort (username, shop_id) uit een request. Faalt nooit."""
    username = None
    try:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            import jwt as pyjwt
            from auth import SECRET_KEY, ALGORITHM
            payload = pyjwt.decode(auth_header[7:], SECRET_KEY, algorithms=[ALGORITHM])
            sub = payload.get("sub")
            if sub is not None:
                username = payload.get("username")
                if not username and str(sub).isdigit():
                    user_id = int(sub)
                    cached = _username_cache.get(user_id)
                    now = time.monotonic()
                    if cached and cached[1] > now:
                        username = cached[0]
                    else:
                        from database import SessionLocal
                        from models import User
                        db = SessionLocal()
                        try:
                            u = db.query(User).filter(User.id == user_id).first()
                            username = u.username if u else None
                        finally:
                            db.close()
                        _username_cache[user_id] = (username, now + USERNAME_CACHE_TTL)
                elif not username:
                    username = str(sub)
    except Exception:
        username = None
    shop_id = None
    try:
        raw = request.headers.get("x-shop-id") or request.query_params.get("shop_id")
        if raw is not None and str(raw).strip():
            shop_id = int(raw)
    except Exception:
        shop_id = None
    return username, shop_id


def estimate_cost_eur(usage_type: str, *, duration_ms=None, tokens_in=None,
                      tokens_out=None, quantity=1.0, rates=None) -> float:
    r = rates or DEFAULT_RATES
    if usage_type == "api_request":
        return r["rate_api_request_eur"]
    if usage_type == "ai_call":
        tokens = (tokens_in or 0) + (tokens_out or 0)
        return tokens * r["rate_ai_token_eur"]
    if usage_type in ("job", "compute"):
        return ((duration_ms or 0) / 1000.0) * r["rate_job_second_eur"]
    if usage_type == "import":
        return (quantity or 1.0) * r["rate_import_row_eur"]
    return 0.0


def record_usage(usage_type: str, module: str = None, *, shop_id: int = None,
                 username: str = None, job_id: str = None,
                 correlation_id: str = None, endpoint: str = None,
                 method: str = None, status_code: int = None,
                 duration_ms: float = None, ai_model: str = None,
                 tokens_in: int = None, tokens_out: int = None,
                 quantity: float = 1.0, cost_eur: float = None,
                 extra: dict = None, flush: bool = False) -> None:
    """Registreer één gebruikseenheid. Gebufferd; faalt nooit hard."""
    row = {
        "occurred_at": datetime.utcnow(),
        "usage_type": usage_type,
        "module": module,
        "shop_id": shop_id,
        "username": username,
        "job_id": job_id,
        "correlation_id": correlation_id,
        "endpoint": endpoint,
        "method": method,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "ai_model": ai_model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "quantity": quantity,
        "cost_eur": cost_eur if cost_eur is not None else estimate_cost_eur(
            usage_type, duration_ms=duration_ms, tokens_in=tokens_in,
            tokens_out=tokens_out, quantity=quantity, rates=current_rates()),
        "extra": extra,
    }
    global _last_flush
    with _buffer_lock:
        _buffer.append(row)
        do_flush = flush or len(_buffer) >= FLUSH_MAX_ROWS or \
            (time.monotonic() - _last_flush) > FLUSH_MAX_SECONDS
    if do_flush:
        flush_usage_buffer()


def flush_usage_buffer() -> int:
    """Schrijf gebufferde rijen in één batch. Retourneert aantal geschreven."""
    global _last_flush
    with _buffer_lock:
        rows = list(_buffer)
        _buffer.clear()
        _last_flush = time.monotonic()
    if not rows:
        return 0
    try:
        from database import SessionLocal
        from models import CostUsageRecord
        db = SessionLocal()
        try:
            try:
                db.bulk_insert_mappings(CostUsageRecord, rows)
                db.commit()
                return len(rows)
            except Exception as batch_exc:
                # Eén ongeldige rij (bv. FK op shop_id) mag nooit de hele
                # batch laten verdwijnen: rollback en rij-voor-rij herproberen.
                db.rollback()
                logger.warning("metering: batch-flush mislukt (%s); rij-voor-rij herproberen.", batch_exc)
                geschreven = 0
                for row in rows:
                    try:
                        db.bulk_insert_mappings(CostUsageRecord, [row])
                        db.commit()
                        geschreven += 1
                    except Exception:
                        db.rollback()
                        # Laatste redmiddel: zonder shop-koppeling opslaan
                        try:
                            row2 = dict(row)
                            row2["shop_id"] = None
                            db.bulk_insert_mappings(CostUsageRecord, [row2])
                            db.commit()
                            geschreven += 1
                        except Exception:
                            db.rollback()
                return geschreven
        finally:
            db.close()
    except Exception as exc:
        logger.error("metering: flush van %d usage-rijen mislukt: %s", len(rows), exc)
        return 0


# ------------------------------------------------------------------
# Rolling in-memory API-metrics per module (Platform Health Center)
# ------------------------------------------------------------------
_metrics_lock = threading.Lock()
# module -> deque[(ts, duration_ms, status_code)]
_request_window: dict[str, deque] = {}
WINDOW_SECONDS = 3600
WINDOW_MAX = 5000


def track_request(module: str, duration_ms: float, status_code: int) -> None:
    now = time.time()
    with _metrics_lock:
        dq = _request_window.setdefault(module, deque(maxlen=WINDOW_MAX))
        dq.append((now, duration_ms, status_code))


def api_metrics_snapshot() -> dict:
    """Per module: requests, gem./p95 responstijd en foutpercentage (laatste uur)."""
    cutoff = time.time() - WINDOW_SECONDS
    out = {}
    with _metrics_lock:
        items = {m: list(dq) for m, dq in _request_window.items()}
    totaal_requests = 0
    totaal_fouten = 0
    alle_duraties: list[float] = []
    for module, rows in items.items():
        rows = [r for r in rows if r[0] >= cutoff]
        if not rows:
            continue
        durs = sorted(r[1] for r in rows)
        errors = sum(1 for r in rows if r[2] >= 500)
        totaal_requests += len(rows)
        totaal_fouten += errors
        alle_duraties.extend(durs)
        out[module] = {
            "requests_last_hour": len(rows),
            "avg_response_ms": round(sum(durs) / len(durs), 1),
            "p95_response_ms": round(durs[int(len(durs) * 0.95) - 1] if len(durs) > 1 else durs[0], 1),
            "error_count": errors,
            "error_rate_pct": round(errors / len(rows) * 100, 2),
        }
    alle_duraties.sort()
    return {
        "per_module": out,
        "totaal": {
            "requests_last_hour": totaal_requests,
            "error_count": totaal_fouten,
            "error_rate_pct": round(totaal_fouten / totaal_requests * 100, 2) if totaal_requests else 0.0,
            "avg_response_ms": round(sum(alle_duraties) / len(alle_duraties), 1) if alle_duraties else 0.0,
            "p95_response_ms": round(alle_duraties[int(len(alle_duraties) * 0.95) - 1], 1) if len(alle_duraties) > 1 else (alle_duraties[0] if alle_duraties else 0.0),
        },
    }


# ------------------------------------------------------------------
# Error ring buffer (drill-down in Platform Health Center)
# ------------------------------------------------------------------
_errors: deque = deque(maxlen=200)


def track_error(*, correlation_id: str, method: str, path: str,
                status_code: int, message: str, module: str = None) -> None:
    _errors.append({
        "timestamp": datetime.utcnow().isoformat(),
        "correlation_id": correlation_id,
        "method": method,
        "path": path,
        "module": module,
        "status_code": status_code,
        "message": (message or "")[:2000],
    })


def recent_errors(limit: int = 100) -> list[dict]:
    return list(_errors)[-limit:][::-1]


def module_from_path(path: str) -> str:
    """Leid de module af uit het API-pad: /api/<module>/..."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "api":
        return parts[1]
    return parts[0] if parts else "root"
