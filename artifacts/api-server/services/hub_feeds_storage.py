"""Private App Storage via Replit's sidecar credentials and the GCS JSON API.

No public ACL, no local fallback, immutable generation-zero writes. Keys are
internal database references, never accepted from a download request.
"""
import os
from urllib.parse import quote
from uuid import uuid4
import httpx
from fastapi import HTTPException

MAX_BYTES = 64 * 1024 * 1024


def location():
    value = os.environ.get("PRIVATE_OBJECT_DIR", "").strip("/")
    if "/" not in value:
        raise HTTPException(503, "Private App Storage is not configured (PRIVATE_OBJECT_DIR)")
    return value.split("/", 1)


def headers():
    # Same external-account exchange as the object-storage skill's GCS client.
    try:
        with httpx.Client(timeout=20, trust_env=False) as client:
            r = client.get("http://127.0.0.1:1106/credential")
            r.raise_for_status()
            subject = r.json()["access_token"]
            r = client.post("http://127.0.0.1:1106/token", data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "audience": "replit", "scope": "https://www.googleapis.com/auth/devstorage.read_write",
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "subject_token_type": "access_token", "subject_token": subject,
            })
            r.raise_for_status()
            return {"Authorization": "Bearer " + r.json()["access_token"]}
    except Exception as exc:
        raise HTTPException(503, "Private App Storage authentication unavailable") from exc


def put(data: bytes, shop_id: int, profile_id: int, suffix: str):
    bucket, prefix = location()
    key = f"{prefix}/hub-feeds/{shop_id}/{profile_id}/{uuid4().hex}.{suffix}"
    try:
        r = httpx.post(f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o",
                       params={"uploadType": "media", "name": key, "ifGenerationMatch": "0"},
                       headers={**headers(), "Content-Type": "application/octet-stream"},
                       content=data, timeout=60)
        r.raise_for_status()
        return key
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Private App Storage write failed") from exc


def get(key: str):
    bucket, prefix = location()
    if not key.startswith(prefix + "/hub-feeds/"):
        raise HTTPException(403, "Invalid private object scope")
    try:
        r = httpx.get(f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}/o/{quote(key, safe='')}",
                      params={"alt": "media"}, headers=headers(), timeout=60)
        r.raise_for_status()
        return r.content
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Private App Storage read failed") from exc


def delete(key: str):
    """Only for rollback of objects that were never committed as immutable versions."""
    bucket, prefix = location()
    if not key.startswith(prefix + "/hub-feeds/"):
        raise HTTPException(403, "Invalid private object scope")
    r = httpx.delete(f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}/o/{quote(key, safe='')}",
                     headers=headers(), timeout=30)
    r.raise_for_status()


def put_pair(data, records, shop_id, profile_id):
    import json
    import logging
    key = put(data, shop_id, profile_id, "csv")
    try:
        return key, put(json.dumps(records, ensure_ascii=False).encode(), shop_id, profile_id, "json")
    except Exception:
        try:
            delete(key)
        except Exception:
            logging.getLogger(__name__).warning("Hub feed uncommitted object cleanup failed")
        raise
