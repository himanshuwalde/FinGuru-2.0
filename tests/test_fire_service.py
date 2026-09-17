"""Unit tests for services/fire_service.py auto-fill helpers.

Covers the real-data defaults the FIRE Planner now starts from:
  * estimate_portfolio_corpus    → bank balances + investment current values
  * estimate_portfolio_volatility → allocation-weighted asset-class σ (clamped)
  * estimate_inflation_rate       → cached live web lookup + graceful fallback

DB calls are fake (the supabase object is never actually hit — the patched
services return canned rows). portfolio_engine.portfolio_summary is also
patched so the tests exercise fire_service logic, not portfolio normalisation.
Navigation: python -m pytest tests/test_fire_service.py
"""
from unittest.mock import MagicMock, patch

from engines.fire_engine import DEFAULT_VOLATILITY_PCT
from services.fire_service import FireService, estimate_inflation_rate


def _make_svc(mock_db, mock_port, accounts, investments):
    """Wire canned rows into the patched db + portfolio layers, return a svc."""
    db = MagicMock()
    db.get_user_accounts.return_value = accounts
    mock_db.return_value = db

    port = MagicMock()
    port.get_investments.return_value = investments
    mock_port.return_value = port

    return FireService(object())  # supabase itself is never touched


def _alloc(*items):
    """Build a portfolio_summary-like dict from (asset_type, current_value) pairs."""
    alloc = [{"asset_type": t, "current": v} for t, v in items]
    total = sum(x["current"] for x in alloc)
    return {"total_current": total, "allocation": alloc}


# ---------------------------------------------------------------- corpus

@patch("engines.portfolio_engine.portfolio_summary")
@patch("services.portfolio_service.get_portfolio_service")
@patch("services.fire_service.get_db_service")
def test_corpus_sums_accounts_and_investments(mock_db, mock_port, mock_summary):
    mock_summary.return_value = _alloc(("Stock", 500_000.0))
    svc = _make_svc(mock_db, mock_port,
                    [{"balance": 50_000.0}, {"balance": 100_000.0}], ["ignored"])
    assert svc.estimate_portfolio_corpus("u1") == 650_000.0


@patch("engines.portfolio_engine.portfolio_summary")
@patch("services.portfolio_service.get_portfolio_service")
@patch("services.fire_service.get_db_service")
def test_corpus_empty_portfolio_is_zero(mock_db, mock_port, mock_summary):
    mock_summary.return_value = _alloc()
    svc = _make_svc(mock_db, mock_port, [], ["ignored"])
    assert svc.estimate_portfolio_corpus("u1") == 0.0


@patch("services.fire_service.get_db_service")
def test_corpus_handles_db_failure(mock_db):
    db = MagicMock()
    db.get_user_accounts.side_effect = Exception("down")
    mock_db.return_value = db
    svc = FireService(object())
    assert svc.estimate_portfolio_corpus("u1") == 0.0


# ---------------------------------------------------------------- volatility

@patch("engines.portfolio_engine.portfolio_summary")
@patch("services.portfolio_service.get_portfolio_service")
@patch("services.fire_service.get_db_service")
def test_vol_equal_split_blends_std_devs(mock_db, mock_port, mock_summary):
    # 50% Stock (18.0) + 50% FD (3.0) → 10.5
    mock_summary.return_value = _alloc(("Stock", 500_000.0), ("FD", 500_000.0))
    svc = _make_svc(mock_db, mock_port, [], ["ignored"])
    assert svc.estimate_portfolio_volatility("u1") == 10.5


@patch("engines.portfolio_engine.portfolio_summary")
@patch("services.portfolio_service.get_portfolio_service")
@patch("services.fire_service.get_db_service")
def test_vol_single_class_uses_its_sigma(mock_db, mock_port, mock_summary):
    mock_summary.return_value = _alloc(("Stock", 1_000_000.0))
    svc = _make_svc(mock_db, mock_port, [], ["ignored"])
    assert svc.estimate_portfolio_volatility("u1") == 18.0

    mock_summary.return_value = _alloc(("FD", 1_000_000.0))
    svc2 = _make_svc(mock_db, mock_port, [], ["ignored"])
    assert svc2.estimate_portfolio_volatility("u1") == 3.0


@patch("engines.portfolio_engine.portfolio_summary")
@patch("services.portfolio_service.get_portfolio_service")
@patch("services.fire_service.get_db_service")
def test_vol_default_when_no_holdings(mock_db, mock_port, mock_summary):
    mock_summary.return_value = {"total_current": 0, "allocation": []}
    svc = _make_svc(mock_db, mock_port, [], ["ignored"])
    assert svc.estimate_portfolio_volatility("u1") == DEFAULT_VOLATILITY_PCT


@patch("engines.portfolio_engine.portfolio_summary")
@patch("services.portfolio_service.get_portfolio_service")
@patch("services.fire_service.get_db_service")
def test_vol_clamped_to_widget_range(mock_db, mock_port, mock_summary):
    # Unknown class maps to catch-all 12.0 — still inside the widget's [1, 40].
    mock_summary.return_value = _alloc(("Weird", 1.0))
    svc = _make_svc(mock_db, mock_port, [], ["ignored"])
    vol = svc.estimate_portfolio_volatility("u1")
    assert 1.0 <= vol <= 40.0


# ---------------------------------------------------------------- inflation

def _reset_cache():
    from services.fire_service import _INFLATION_CACHE
    _INFLATION_CACHE["value"] = None
    _INFLATION_CACHE["ts"] = 0.0


def test_inflation_parses_percent_from_search():
    _reset_cache()
    with patch("services.fire_service.search_web_text",
               return_value="India inflation rate: 6.52% (YoY, May 2025)"):
        assert estimate_inflation_rate("India") == 6.52


def test_inflation_falls_back_to_default_on_empty_search():
    _reset_cache()
    with patch("services.fire_service.search_web_text", return_value=""):
        assert estimate_inflation_rate("India") == 6.0