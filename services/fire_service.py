"""
FIRE Service — Supabase persistence + engine orchestration for the
retirement planner. One `fire_profiles` row per user (upserted), a history of
`fire_simulations` runs, and a sensible default monthly expense derived from
the user's real transactions (average spend of recent months).

Auto-fill helpers estimate the user's current corpus (bank balances +
investments) and portfolio volatility (weighted by asset-class allocation)
from the same data the Portfolio / Net Worth pages use, so the FIRE inputs
start grounded in the user's real financial picture.
"""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional

from supabase import Client

from engines import fire_engine, portfolio_engine
from services.database import get_db_service
from services.insurance_search import search_web_text


class FireService:
    def __init__(self, supabase: Client):
        self.supabase = supabase
        self.db = get_db_service(supabase)

    # ------------------------------------------------------------ read

    def get_profile(self, user_id: str) -> Optional[Dict]:
        try:
            res = self.supabase.table("fire_profiles") \
                .select("*") \
                .eq("user_id", user_id) \
                .maybe_single().execute()
            return res.data
        except Exception:
            return None

    def estimate_monthly_expense(self, user_id: str) -> float:
        """Average monthly spend over the last 3 months of real transactions."""
        try:
            df = self.db.get_historical_expenses(user_id, months_back=3)
            if df.empty:
                return 30000.0
            # %Y-%m group → mean of monthly totals
            monthly = df.assign(_m=df["transaction_time"].dt.to_period("M")) \
                .groupby("_m")["amount"].sum()
            return round(float(monthly.mean()), 0)
        except Exception:
            return 30000.0

    def estimate_portfolio_corpus(self, user_id: str) -> float:
        """Current corpus = bank balances + investment current values (the same
        asset base the Net Worth page shows, minus nothing). 0.0 when the user
        has no accounts or holdings yet (never raises)."""
        try:
            accounts = self.db.get_user_accounts(user_id)
            liquid = sum(float(a.get("balance") or 0) for a in accounts)

            from services.portfolio_service import get_portfolio_service
            rows = get_portfolio_service(self.supabase).get_investments(user_id)
            summary = portfolio_engine.portfolio_summary(rows)
            inv_total = float(summary.get("total_current") or 0)

            return round(liquid + inv_total, 2)
        except Exception:
            return 0.0

    def estimate_portfolio_volatility(self, user_id: str) -> float:
        """Blended portfolio volatility (% p.a.) weighted by the user's real
        allocation: equity holdings carry typical market volatility (Stock 18%,
        MF 15%) while stable assets contribute far less (FD 3%, Property 10%,
        Gold 15%). Falls back to the engine default (14%) with no data. The
        result is an estimate (the portfolio page records point-in-time values,
        not price history) and the widget lets the user override it."""
        try:
            from services.portfolio_service import get_portfolio_service

            # Stored current values are fine for a heuristic weight default —
            # no live-price overlay (that would hit the network per ticker on
            # every page render for a number that's near-fixed day to day).
            rows = get_portfolio_service(self.supabase).get_investments(user_id)
            summary = portfolio_engine.portfolio_summary(rows)
            alloc = summary.get("allocation") or []
            if not alloc:
                return fire_engine.DEFAULT_VOLATILITY_PCT

            total = sum(float(a.get("current") or 0) for a in alloc)
            if total <= 0:
                return fire_engine.DEFAULT_VOLATILITY_PCT

            weighted = sum(
                float(a.get("current") or 0) * _VOLATILITY_BY_ASSET.get(str(a.get("asset_type")), 12.0)
                for a in alloc
            ) / total
            return round(min(40.0, max(1.0, weighted)), 1)
        except Exception:
            return fire_engine.DEFAULT_VOLATILITY_PCT

    def get_recent_simulations(self, user_id: str, limit: int = 5) -> List[Dict]:
        try:
            res = self.supabase.table("fire_simulations") \
                .select("id, target_age, required_corpus, projected_corpus, "
                        "probability_pct, p5, p95, created_at") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(limit).execute()
            return res.data or []
        except Exception:
            return []

    # ------------------------------------------------------------ write

    def save_profile(self, user_id: str, data: Dict) -> bool:
        try:
            payload = {
                "user_id": user_id,
                "current_age": int(data.get("current_age") or 22),
                "target_retirement_age": int(data.get("target_retirement_age") or 45),
                "monthly_expense": float(data.get("monthly_expense") or 0),
                "monthly_investment": float(data.get("monthly_investment") or 0),
                "current_corpus": float(data.get("current_corpus") or 0),
                "expected_return_pct": float(data.get("expected_return_pct") or 10),
                "inflation_pct": float(data.get("inflation_pct") or 6),
                "safe_withdrawal_rate_pct": float(data.get("safe_withdrawal_rate_pct") or 4),
            }
            self.supabase.table("fire_profiles") \
                .upsert(payload, on_conflict="user_id").execute()
            return True
        except Exception as e:
            print(f"[fire_service] save_profile failed: {e}")
            return False

    def run_and_save(self, user_id: str, data: Dict, seed: Optional[int] = None) -> Optional[Dict]:
        """Run the Monte Carlo and store the result in fire_simulations."""
        try:
            result = fire_engine.fire_simulation(
                current_age=data.get("current_age", 22),
                target_retirement_age=data.get("target_retirement_age", 45),
                monthly_expense=data.get("monthly_expense", 0),
                monthly_investment=data.get("monthly_investment", 0),
                current_corpus=data.get("current_corpus", 0),
                expected_return_pct=data.get("expected_return_pct", 10),
                inflation_pct=data.get("inflation_pct", 6),
                safe_withdrawal_rate_pct=data.get("safe_withdrawal_rate_pct", 4),
                volatility_pct=float(data.get("volatility_pct") or
                                     fire_engine.DEFAULT_VOLATILITY_PCT),
                n_simulations=int(data.get("n_simulations", 3000)),
                seed=seed,
            )
            profile = self.get_profile(user_id) or {}
            payload = {
                "user_id": user_id,
                "fire_profile_id": profile.get("id"),
                "target_age": int(result["target_retirement_age"]),
                "required_corpus": result["required_corpus"],
                "projected_corpus": result["median_corpus"],
                "probability_pct": result["probability_pct"],
                "p5": result["p5_corpus"],
                "p95": result["p95_corpus"],
                "simulations_count": result["n_simulations"],
            }
            res = self.supabase.table("fire_simulations").insert(payload).execute()
            rows = res.data or []
            if rows:
                # Stamp the saved record's id onto the returned result so the
                # page can pinpoint ("Clear last result") and match this exact
                # run against the history rows.
                result = dict(result)
                result["id"] = rows[0]["id"]
            return result
        except Exception as e:
            print(f"[fire_service] run_and_save failed: {e}")
            return None

    def delete_simulation(self, user_id: str, simulation_id: str) -> bool:
        """Permanently delete one historical FIRE run. Owner-guarded so a user
        can never remove another user's record (RLS backs this up too)."""
        try:
            self.supabase.table("fire_simulations") \
                .delete() \
                .eq("id", simulation_id) \
                .eq("user_id", user_id) \
                .execute()
            return True
        except Exception as e:
            print(f"[fire_service] delete_simulation failed: {e}")
            return False


# Typical annualised volatility by asset class — used to estimate the user's
# blended portfolio volatility from the allocation weights returned by
# portfolio_engine.portfolio_summary().  These are long-run averages for a
# broad Indian-market context and are only a starting point; the user can
# override the number once it auto-fills.
_VOLATILITY_BY_ASSET: Dict[str, float] = {
    "Stock":        18.0,   # Nifty 50 long-run σ
    "Mutual Fund":  15.0,   # diversified equity MF
    "FD":            3.0,   # near-zero interest-rate vol
    "Gold":         15.0,   # gold price vol (India, INR)
    "Property":     10.0,   # real-estate valuation vol
    "Other":        12.0,   # catch-all
}

# Cache for the live-inflation web search: (value, timestamp).  The search
# hits a free endpoint and the result changes only monthly, so 24-hour
# freshness is more than sufficient.
_INFLATION_CACHE: Dict[str, object] = {"value": None, "ts": 0.0}
_INFLATION_TTL = 86400.0  # 24 h


def estimate_inflation_rate(country: str = "India") -> float:
    """Return the current CPI inflation rate for *country* via web search.

    Result is cached for 24 hours so repeated page loads are free.  On any
    failure the last cached value is returned; if there
    has never been a successful fetch the engine default (6.0 %) is used.
    """
    now = time.time()
    if (_INFLATION_CACHE["value"] is not None
            and now - _INFLATION_CACHE["ts"] < _INFLATION_TTL):
        return float(_INFLATION_CACHE["value"])

    try:
        query = f"current inflation rate {country} 2025 CPI annual"
        raw = search_web_text(query, count=5)
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(raw))
        if m:
            val = float(m.group(1))
            _INFLATION_CACHE["value"] = val
            _INFLATION_CACHE["ts"] = now
            return val
    except Exception:
        pass

    # Fallback: return last cached value, or engine default
    if _INFLATION_CACHE["value"] is not None:
        return float(_INFLATION_CACHE["value"])
    return 6.0


def get_fire_service(supabase: Client) -> FireService:
    return FireService(supabase)