"""Run the actual main.py middleware without its database startup/lifespan."""
import ast
import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
import time
import uuid
import json
import logging

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import pytest


@pytest.mark.parametrize("middleware", ["authz_middleware", "observability_middleware"])
def test_waiting_database_work_does_not_block_health(middleware):
    async def exercise():
        app = FastAPI()
        entered, release = threading.Event(), threading.Event()

        def slow(*args, **kwargs):
            entered.set()
            release.wait(2)
            return False if middleware == "authz_middleware" else ("test", 1)

        noop = lambda *a, **kw: None
        namespace = {
            "app": app, "Request": object, "asyncio": asyncio,
            "JSONResponse": JSONResponse, "_permission_denied": slow,
            "_authz": SimpleNamespace(
                required_action_permission=lambda *a: None,
                required_permission_for_path=lambda p: None if p == "/api/healthz" else "pricing.view"),
            "_pyjwt": SimpleNamespace(decode=lambda *a, **kw: {"sub": "1"}),
            "_auth_utils": SimpleNamespace(SECRET_KEY="unused", ALGORITHM="unused"),
            "_metering": SimpleNamespace(module_from_path=noop, track_request=noop,
                actor_from_request=slow, record_usage=noop, track_error=noop),
            "_METERING_EXCLUDE": ("/api/healthz",), "_time": time,
            "uuid": uuid, "json": json, "logger": logging.getLogger(__name__),
        }
        tree = ast.parse((Path(__file__).parents[1] / "main.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == middleware)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "main.py", "exec"), namespace)

        @app.get("/api/healthz")
        async def health():
            return {"status": "ok"}

        @app.get("/api/recommendations")
        async def data():
            return {"ok": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            request = asyncio.create_task(client.get("/api/recommendations", headers={"Authorization": "Bearer test"}))
            try:
                started = await asyncio.to_thread(entered.wait, 1)
                assert started
                # The blocked operation has not finished, yet health must respond.
                assert not request.done()
                response = await asyncio.wait_for(client.get("/api/healthz"), .5)
                assert response.status_code == 200
            finally:
                release.set()
                await request

    asyncio.run(exercise())
