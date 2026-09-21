from datetime import datetime

from dateutil.relativedelta import relativedelta
from fastapi.testclient import TestClient

import backend.routers.track as track
from backend.main import app
from services import recommendation_service
from tests.conftest import make_token

client = TestClient(app)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, data):
        self._data = data
        self._single = False

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        data = self._data[0] if self._single and isinstance(self._data, list) and self._data else self._data
        return _FakeResult(data)


class FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _FakeQuery(self.tables.get(name, []))


ACCOUNTS = [
    {"id": "a1", "account_name": "HDFC", "is_primary": True, "monthly_budget": 40000, "balance": 50000.0},
    {"id": "a2", "account_name": "Cash", "is_primary": False, "monthly_budget": 10000, "balance": 5000.0},
]

_NOW = datetime.now()


def _tx(months_back: int, day: int, type_: str, amount: float, category="Food"):
    when = _NOW - relativedelta(months=months_back)
    when = when.replace(day=min(day, 28))
    return {
        "account_id": "a1",
        "amount": amount,
        "type": type_,
        "category": category,
        "description": f"{category} run",
        "transaction_time": when.isoformat(),
        "is_recurring": False,
        "created_at": when.isoformat(),
    }


TRANSACTIONS = [
    # current month
    _tx(0, 2, "Income", 50000, "Salary"),
    _tx(0, 5, "Expense", 12000, "Rent"),
    _tx(0, 12, "Expense", 14150, "Food"),
    # previous month
    _tx(1, 2, "Income", 48000, "Salary"),
    _tx(1, 5, "Expense", 12000, "Rent"),
    _tx(1, 12, "Expense", 12000, "Food"),
    # older months (one net-loss month to exercise the zero-split chart path)
    _tx(2, 2, "Income", 45000, "Salary"),
    _tx(2, 6, "Expense", 51000, "Travel"),
    _tx(3, 2, "Income", 47000, "Salary"),
    _tx(3, 6, "Expense", 30000, "Travel"),
]

FAKE_CONTEXT = {
    "health_score": {
        "overall": 72,
        "verb": "Good",
        "flags": [{"severity": "warning", "message": "No investments yet."}],
    },
    "financial": {},
    "kpis": {"net_worth": 1240500.0},
}


def _install(monkeypatch):
    fake = FakeSupabase(
        {
            "accounts": ACCOUNTS,
            "transactions": TRANSACTIONS,
            "profiles": [{"id": "user-123", "full_name": "Himanshu Walde", "email": "fin@example.com"}],
        }
    )
    monkeypatch.setattr(track, "user_client", lambda token: fake)
    monkeypatch.setattr(
        recommendation_service, "build_financial_context", lambda client, uid: FAKE_CONTEXT
    )


def test_dashboard_happy_path(fake_jwks, monkeypatch):
    _install(monkeypatch)
    response = client.get("/api/track/dashboard", headers={"Authorization": f"Bearer {make_token()}"})
    assert response.status_code == 200
    body = response.json()

    assert body["display_name"] == "Himanshu"
    assert body["month_label"] == _NOW.strftime("%B %Y")
    assert body["net_worth"] == 1240500.0

    # this month: 50000 in, 26150 out
    assert body["income"]["value"] == 50000
    assert body["expense"]["value"] == 26150
    assert body["net"]["value"] == 23850
    # MoM: income +4.2%, expense +9.0%, net -0.6%
    assert body["income"]["mom_pct"] == 4.2
    assert body["expense"]["mom_pct"] == 9.0
    assert body["net"]["mom_pct"] == -0.6

    assert body["budget"]["monthly_budget"] == 50000
    assert body["budget"]["spent"] == 26150
    assert body["budget"]["percent_used"] == 52.3
    assert body["budget"]["status"] == "ok"

    assert body["health"]["overall"] == 72
    assert body["health"]["verb"] == "Good"
    assert body["health"]["flags"][0]["severity"] == "warning"

    assert len(body["cashflow"]) == 6
    current = body["cashflow"][-1]
    assert current["income"] == 50000
    assert current["net"] == 23850
    loss_month = body["cashflow"][3]  # 2 months back: 45000 in, 51000 out
    assert loss_month["net"] == -6000


def test_dashboard_requires_auth():
    response = client.get("/api/track/dashboard")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_dashboard_rejects_invalid_token(fake_jwks):
    response = client.get("/api/track/dashboard", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid or expired token"


def test_dashboard_with_no_data(fake_jwks, monkeypatch):
    fake = FakeSupabase({"accounts": [], "transactions": [], "profiles": []})
    monkeypatch.setattr(track, "user_client", lambda token: fake)
    monkeypatch.setattr(
        recommendation_service, "build_financial_context", lambda client, uid: FAKE_CONTEXT
    )
    response = client.get("/api/track/dashboard", headers={"Authorization": f"Bearer {make_token()}"})
    assert response.status_code == 200
    body = response.json()

    # No profile row → falls back to the JWT email prefix
    assert body["display_name"] == "Fin"
    assert body["income"]["mom_pct"] is None
    assert body["budget"]["status"] == "none"
    assert body["budget"]["monthly_budget"] == 0
    assert all(p["net"] == 0 for p in body["cashflow"])


def test_dashboard_service_unavailable_when_supabase_not_configured(fake_jwks, monkeypatch):
    def _raise(token):
        raise track.SupabaseNotConfigured("missing env")

    monkeypatch.setattr(track, "user_client", _raise)
    response = client.get("/api/track/dashboard", headers={"Authorization": f"Bearer {make_token()}"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
