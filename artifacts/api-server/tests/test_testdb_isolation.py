"""
Regressietests voor de testdatabase-isolatie in conftest (taak #312):
de suite mag nooit tegen de app-database draaien, ook niet via
libpq-trucs zoals een `?dbname=`-queryparameter of `service=`-indirectie.
"""
import os

import pytest

from tests.conftest import (
    _assert_distinct_databases,
    _derive_test_url,
    _effective_dbname,
)


def test_derive_behoudt_sslmode_en_query_opties():
    url = "postgresql://u:p@host:5432/appdb?sslmode=require&connect_timeout=5"
    t = _derive_test_url(url)
    assert "/appdb_test" in t
    assert "sslmode=require" in t
    assert "connect_timeout=5" in t


def test_dbname_queryparam_overschrijft_pad():
    # libpq laat ?dbname= het pad overschrijven; de guard moet dat zien.
    url = "postgresql://u:p@host/appdb_test?dbname=appdb"
    assert _effective_dbname(url) == "appdb"


def test_guard_weigert_dbname_bypass():
    app = "postgresql://u:p@host/appdb"
    sneaky = "postgresql://u:p@host/appdb_test?dbname=appdb"
    with pytest.raises(RuntimeError, match="geweigerd"):
        _assert_distinct_databases(app, sneaky)


def test_derive_strip_dbname_param():
    url = "postgresql://u:p@host/pad_db?dbname=appdb&sslmode=require"
    t = _derive_test_url(url)
    assert "dbname=" not in t.split("?", 1)[1]
    assert "/appdb_test" in t
    _assert_distinct_databases(url, t)  # mag niet raisen


def test_guard_weigert_service_indirectie():
    with pytest.raises(RuntimeError, match="service"):
        _effective_dbname("postgresql:///?service=prod")


def test_suite_draait_echt_op_testdatabase():
    # De omgeving is door conftest omgezet: DATABASE_URL wijst naar de
    # testdatabase en verschilt van de originele app-URL.
    orig = os.environ.get("APP_DATABASE_URL_ORIGINAL")
    assert orig, "conftest heeft de app-URL niet bewaard"
    assert _effective_dbname(os.environ["DATABASE_URL"]) != _effective_dbname(orig)
    assert _effective_dbname(os.environ["DATABASE_URL"]).endswith("_test")
