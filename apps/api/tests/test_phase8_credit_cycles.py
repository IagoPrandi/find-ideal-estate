import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from modules.credits import service as credits_service  # noqa: E402


class _FakeMappingsResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeScalarResult:
    def __init__(self, value=None):
        self._value = value

    def scalar(self):
        return self._value


class _FakeResult:
    def __init__(self, row=None, scalar=None):
        self._row = row
        self._scalar = scalar

    def mappings(self):
        return _FakeMappingsResult(self._row)

    def scalar(self):
        return self._scalar


class _FakeConn:
    def __init__(self, *, user_credits_row: dict, active_plan_row: dict | None = None, fallback_plan_row: dict | None = None):
        self.user_credits_row = dict(user_credits_row)
        self.active_plan_row = dict(active_plan_row) if active_plan_row is not None else None
        self.fallback_plan_row = dict(fallback_plan_row) if fallback_plan_row is not None else None
        self.ledger_entries: list[dict] = []

    async def execute(self, statement, params=None):
        query = str(statement)
        params = params or {}

        if "FROM user_credits" in query and "WHERE user_id = :user_id" in query and query.lstrip().startswith("SELECT"):
            return _FakeResult(row=dict(self.user_credits_row))

        if "FROM plan_activations pa" in query and "JOIN plans p ON p.id = pa.plan_id" in query:
            return _FakeResult(row=dict(self.active_plan_row) if self.active_plan_row is not None else None)

        if "WHERE p.slug = 'free'" in query:
            return _FakeResult(row=dict(self.fallback_plan_row) if self.fallback_plan_row is not None else None)

        if "UPDATE user_credits" in query and "SET plan_id = :plan_id" in query:
            self.user_credits_row.update(
                {
                    "plan_id": params["plan_id"],
                    "cycle_credits": params["cycle_credits"],
                    "rollover_balance": 0,
                    "monthly_quota": params["monthly_quota"],
                    "cycle_started_at": params["cycle_started_at"],
                    "cycle_ends_at": params["cycle_ends_at"],
                }
            )
            return _FakeResult()

        if "INSERT INTO credit_ledger" in query:
            self.ledger_entries.append(dict(params))
            return _FakeResult()

        if "UPDATE user_credits" in query and "SET cycle_credits = :cycle" in query:
            self.user_credits_row.update(
                {
                    "cycle_credits": params["cycle"],
                    "rollover_balance": params["rollover"],
                    "legacy_balance": params["legacy"],
                }
            )
            return _FakeResult()

        raise AssertionError(f"Query não tratada no teste: {query}")


class _FakeBeginContext:
    def __init__(self, conn: _FakeConn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn: _FakeConn):
        self._conn = conn

    def begin(self):
        return _FakeBeginContext(self._conn)


@pytest.mark.anyio
async def test_get_user_credits_reseta_ciclo_vencido_para_a_cota_do_plano_ativo(monkeypatch):
    now = datetime.now(tz=timezone.utc)
    conn = _FakeConn(
        user_credits_row={
            "plan_id": uuid4(),
            "cycle_credits": 120,
            "rollover_balance": 45,
            "legacy_balance": 17,
            "cycle_started_at": now - timedelta(days=40),
            "cycle_ends_at": now - timedelta(days=1),
            "monthly_quota": 120,
        },
        active_plan_row={
            "id": uuid4(),
            "monthly_credits": 4000,
            "cycle_length_days": 30,
        },
    )

    monkeypatch.setattr(credits_service, "get_engine", lambda: _FakeEngine(conn))

    credits = await credits_service.get_user_credits(uuid4())

    assert credits.cycle == 4000
    assert credits.rollover == 0
    assert credits.legacy == 17
    assert credits.total == 4017
    assert credits.monthly_quota == 4000
    assert credits.cycle_ends_at is not None and credits.cycle_ends_at > now
    assert len(conn.ledger_entries) == 2


@pytest.mark.anyio
async def test_check_and_consume_reseta_ciclo_vencido_antes_de_consumir(monkeypatch):
    now = datetime.now(tz=timezone.utc)
    conn = _FakeConn(
        user_credits_row={
            "plan_id": uuid4(),
            "cycle_credits": 5,
            "rollover_balance": 0,
            "legacy_balance": 0,
            "cycle_started_at": now - timedelta(days=50),
            "cycle_ends_at": now - timedelta(days=2),
            "monthly_quota": 5,
        },
        active_plan_row=None,
        fallback_plan_row={
            "id": uuid4(),
            "monthly_credits": 350,
            "cycle_length_days": 30,
        },
    )

    monkeypatch.setattr(credits_service, "get_engine", lambda: _FakeEngine(conn))

    credits = await credits_service.check_and_consume(uuid4(), "zone_generation")

    assert credits.cycle == 330
    assert credits.rollover == 0
    assert credits.legacy == 0
    assert credits.total == 330
    assert credits.monthly_quota == 350
    assert credits.cycle_ends_at is not None and credits.cycle_ends_at > now
    assert conn.user_credits_row["cycle_credits"] == 330
