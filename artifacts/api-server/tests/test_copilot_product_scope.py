"""
Copilot-productscope-enforcement (taak #301): een actief Product-filter is
een server-side toolconstraint in _execute_tool — geen prompttekst.

Bewijst dat met een actieve productscope:
- sku_id-tools altijd op de gescopeerde SKU draaien (ook bij afwijkende
  model-argumenten);
- entity_id-tools (traffic, signalen) nooit categoriebreed of met een
  andere entiteit kunnen draaien;
- tools zonder product-parameter onaangetast blijven (categoriescope via
  hierarchy_node_ids blijft gelden).
"""
import os
import sys
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_gateway
import models

SCOPE = {"sku_id": "SCOPED-SKU-1", "label": "SKU SCOPED-SKU-1 – Testproduct",
         "source": "global_filter"}


def _user(role="admin"):
    return models.User(id=1, username="t301", role=role, is_active=True)


def _run(name, arguments):
    captured = {}

    def fake_fn(db, user, shop_id=None, **kwargs):
        captured.update(kwargs)
        return {"items": [], "data_available": True}

    sem = ai_gateway.SEMANTIC_FUNCTIONS[name]
    fake_sem = SimpleNamespace(name=sem.name, description=sem.description,
                               required_roles=sem.required_roles, fn=fake_fn)
    with mock.patch.dict(ai_gateway.SEMANTIC_FUNCTIONS, {name: fake_sem}):
        result, meta = ai_gateway._execute_tool(
            None, _user(), name, dict(arguments),
            shop_id=1, product_scope=SCOPE)
    return captured, meta


def test_sku_id_tool_is_pinned_to_scoped_sku():
    captured, meta = _run("get_product_performance", {"sku_id": "ANDERE-SKU"})
    assert captured["sku_id"] == SCOPE["sku_id"]
    assert meta["product_scope"]["sku_id"] == SCOPE["sku_id"]


def test_entity_id_tool_without_argument_is_pinned():
    captured, meta = _run("get_traffic_summary", {"days": 30})
    assert captured["entity_id"] == SCOPE["sku_id"]
    assert meta["product_scope"]["sku_id"] == SCOPE["sku_id"]


def test_entity_id_tool_with_other_entity_is_overridden():
    captured, _ = _run("get_active_signals", {"entity_id": "CAT-99"})
    assert captured["entity_id"] == SCOPE["sku_id"]


def test_tool_without_product_param_unaffected():
    captured, meta = _run("get_margin_erosion", {"days": 30, "limit": 5})
    assert "sku_id" not in captured and "entity_id" not in captured
    assert "product_scope" not in meta


def test_no_scope_means_no_pinning():
    captured = {}

    def fake_fn(db, user, shop_id=None, **kwargs):
        captured.update(kwargs)
        return {"items": [], "data_available": True}

    sem = ai_gateway.SEMANTIC_FUNCTIONS["get_traffic_summary"]
    fake_sem = SimpleNamespace(name=sem.name, description=sem.description,
                               required_roles=sem.required_roles, fn=fake_fn)
    with mock.patch.dict(ai_gateway.SEMANTIC_FUNCTIONS,
                         {"get_traffic_summary": fake_sem}):
        ai_gateway._execute_tool(None, _user(), "get_traffic_summary",
                                 {"entity_id": "VRIJ-1"}, shop_id=1)
    assert captured["entity_id"] == "VRIJ-1"
