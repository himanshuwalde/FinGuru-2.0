"""
Context Builder — deterministic financial "tools" for the CA chatbot.
Every tool reads real user data from Supabase and runs the SAME pure engines
that power the screens. The outputs are serialized into the chatbot prompt,
so the bot can never disagree with the numbers on screen.

Latency / token discipline: the chatbot loads only the tools its intent needs
(see ai/intent_router.py), not the entire financial picture.
"""
from __future__ import annotations

import json
from typing import Callable, Dict, List, Tuple

from supabase import Client

from engines import tax_engine
from utils.currency import (DEFAULT_CODE, fmt_money, symbol, to_display)
from services.database import get_db_service
from services.fire_service import get_fire_service
from services.market_data_service import live_price
from services.networth_service import get_networth_service
from services.portfolio_service import get_portfolio_service
from services.tax_service import get_tax_service

DEFAULT_AY = "2026-27"


def _fmt_money(v: float) -> str:
    return fmt_money(v)


def _pprune(d: Dict, max_chars: int = 1_200_000) -> str:
    """Serialize dict → JSON, trimmed for the prompt (safety cap)."""
    s = json.dumps(d, default=float, indent=1)
    return s[:max_chars]


# ------------------------------------------------------------------- currency

# Which tool-result fields are money (stored INR) vs percentages/scores/ages.
# "ALL" → every numeric in that result is a money amount. A set → only those
# keys (and their subtrees, e.g. "allocation") are money.
_MONEY_SPECS: Dict[str, object] = {
    "tax_calculator": "ALL",
    "net_worth": "ALL",
    "spending_summary": {"avg_monthly_expense", "last_month_expense",
                         "avg_monthly_income"},
    "portfolio_summary": {"total_invested", "total_current", "absolute_return",
                          "allocation"},
    "fire_status": {"future_monthly_expense", "annual_expense_at_retirement",
                    "required_corpus", "median_corpus", "p5_corpus",
                    "p95_corpus", "shortfall_vs_median"},
    # NOTE: market_indices intentionally ABSENT — NIFTY points / USD-per-oz /
    # FX rates are not money amounts and must never go through to_display()
    # (a USD-display user would get an index level "converted" by the FX rate).
}


def _map_numeric(o: object) -> object:
    """Recursively convert every numeric in a structure to the display currency."""
    if isinstance(o, dict):
        return {k: _map_numeric(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_map_numeric(x) for x in o]
    if isinstance(o, bool):
        return o
    if isinstance(o, (int, float)):
        return to_display(float(o))
    return o


def _map_keys(o: object, keep: set) -> object:
    """Convert numerics only under the money keys (recursively) — everything
    else (percentages, scores, ages, strings) passes through untouched."""
    if isinstance(o, dict):
        return {k: (_map_numeric(v) if k in keep else _map_keys(v, keep))
                for k, v in o.items()}
    if isinstance(o, list):
        return [_map_keys(x, keep) for x in o]
    return o


def _in_display_currency(tool: str, data: Dict) -> Dict:
    """Return a copy of tool output with stored-INR amounts re-expressed in the
    user's display currency (identity when INR). Never touches the raw dict."""
    spec = _MONEY_SPECS.get(tool)
    if spec == "ALL":
        return _map_numeric(data)
    if isinstance(spec, set):
        return _map_keys(data, spec)
    return data


def _user_settings() -> Dict:
    """Current currency + persona from session state (safe offline: INR +
    default persona)."""
    try:
        import streamlit as st
        cur = st.session_state.get("preferred_currency") or DEFAULT_CODE
        return {
            "currency": cur,
            "symbol": symbol(cur),
            "tone": st.session_state.get("ai_tone") or "Strict Accountant",
            "phase": st.session_state.get("financial_phase") or "Building Wealth",
            "risk": st.session_state.get("risk_tolerance") or "Moderate",
        }
    except Exception:
        return {"currency": DEFAULT_CODE, "symbol": symbol(DEFAULT_CODE),
                "tone": "Strict Accountant", "phase": "Building Wealth",
                "risk": "Moderate"}


def _user_risk() -> str:
    """The user's saved investment risk tolerance (defaults to Moderate)."""
    try:
        import streamlit as st
        return st.session_state.get("risk_tolerance") or "Moderate"
    except Exception:
        return "Moderate"


# ------------------------------------------------------------------- tools


def tool_tax_calculator(supabase: Client, user_id: str) -> Dict:
    """Compute fresh tax (both regimes) from the user's saved declaration."""
    svc = get_tax_service(supabase)
    profile = svc.get_profile(user_id, DEFAULT_AY)
    if not profile:
        return {"status": "no_data",
                "note": "No saved tax declaration — run Tax Planner first."}
    inputs = svc.profile_to_inputs(profile, DEFAULT_AY)
    result = tax_engine.compute_tax(inputs)
    return {
        "status": "ok",
        "assessment_year": DEFAULT_AY,
        "recommended_regime": result["recommended_regime"],
        "potential_saving": result["potential_saving"],
        "regimes": {
            "old": {k: v for k, v in result["regimes"]["old"].items()
                    if k not in ("breakdown",)},
            "new": {k: v for k, v in result["regimes"]["new"].items()
                    if k not in ("breakdown",)},
        },
        "top_deductions": {
            k: v for k, v in result["regimes"]["old"].get("deductions", {}).items()
        },
    }


def tool_tax_saving_opportunities(supabase: Client, user_id: str) -> Dict:
    svc = get_tax_service(supabase)
    profile = svc.get_profile(user_id, DEFAULT_AY)
    if not profile:
        return {"status": "no_data", "opportunities": [],
                "note": "No saved tax declaration — run Tax Planner first."}
    inputs = svc.profile_to_inputs(profile, DEFAULT_AY)
    result = tax_engine.compute_tax(inputs)
    return {
        "status": "ok",
        "assessment_year": DEFAULT_AY,
        "opportunities": result["tax_saving_opportunities"],
    }


def tool_portfolio_summary(supabase: Client, user_id: str) -> Dict:
    svc = get_portfolio_service(supabase)
    s = svc.get_summary(user_id)
    if not s["holdings"]:
        return {"status": "no_data", "note": "No investments added yet.",
                "as_of": s["as_of"]}
    health, insights = svc.get_health(user_id, _user_risk())
    return {
        "status": "ok",
        "as_of": s["as_of"],
        "total_invested": s["total_invested"],
        "total_current": s["total_current"],
        "absolute_return": s["absolute_return"],
        "return_pct": s["return_pct"],
        "xirr_pct": s["xirr_pct"],
        "allocation": s["allocation"],
        "health_score": health,
        "health_insights": insights,
    }


def tool_net_worth(supabase: Client, user_id: str) -> Dict:
    svc = get_networth_service(supabase)
    n = svc.compute_networth(user_id)
    return {
        "status": "ok",
        "as_of": n["as_of"],
        "liquid_assets": n["liquid_assets"],
        "investments_total": n["investments_total"],
        "total_assets": n["total_assets"],
        "total_liabilities": n["total_liabilities"],
        "net_worth": n["net_worth"],
        "liabilities": n["liabilities_breakdown"],
    }


def tool_fire_status(supabase: Client, user_id: str) -> Dict:
    svc = get_fire_service(supabase)
    profile = svc.get_profile(user_id)
    if not profile:
        return {"status": "no_data", "note": "No FIRE profile — run FIRE Planner."}
    # Read-only recompute with a fixed seed so chat never writes to the DB.
    from engines import fire_engine
    r = fire_engine.fire_simulation(
        current_age=profile.get("current_age", 22),
        target_retirement_age=profile.get("target_retirement_age", 45),
        monthly_expense=profile.get("monthly_expense", 0),
        monthly_investment=profile.get("monthly_investment", 0),
        current_corpus=profile.get("current_corpus", 0),
        expected_return_pct=profile.get("expected_return_pct", 10),
        inflation_pct=profile.get("inflation_pct", 6),
        safe_withdrawal_rate_pct=profile.get("safe_withdrawal_rate_pct", 4),
        n_simulations=1500, seed=42)
    return {"status": "ok", **r}


def tool_spending_summary(supabase: Client, user_id: str) -> Dict:
    import datetime
    db = get_db_service(supabase)
    exp = db.get_historical_expenses(user_id, months_back=3)
    if exp.empty:
        return {"status": "no_data", "note": "No expense transactions in the "
                                             "last 3 months."}
    exp = exp.assign(_m=exp["transaction_time"].dt.to_period("M"))
    monthly = exp.groupby("_m")["amount"].agg(["sum", "mean"]).reset_index()
    months = [str(r["_m"]) for r in monthly.to_dict("records")]

    # Determine the actual month for the most recent data
    current_month = datetime.datetime.now().month
    current_year = datetime.datetime.now().year
    last_period = monthly.iloc[-1]["_m"]
    last_month_is_current = (last_period.year == current_year and last_period.month == current_month)

    # Format the month name nicely for AI responses
    month_names = ["", "January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    last_month_display = f"{month_names[last_period.month]} {last_period.year}"

    return {
        "status": "ok",
        "months_covered": months,
        "avg_monthly_expense": float(monthly["sum"].mean()),
        "last_month_expense": float(monthly.iloc[-1]["sum"]),
        "last_month_name": last_month_display,  # e.g., "September 2026" for AI
        "last_month_is_current": last_month_is_current,
        "time_period_label": "this month's" if last_month_is_current else "last month's",
        "avg_monthly_income": 0,  # incomes are set by the service below when present
        "note": "Expense figures only; income is captured via Net Worth / FIRE. "
                "Use 'time_period_label' to describe when the last_month_expense occurred - "
                "say 'this month's' if last_month_is_current is true, otherwise 'last month's'.",
    }


# (ticker, display name, unit) — India-relevant references. Index levels are in
# POINTS (never a ₹ amount); Gold is USD per troy ounce; USD/INR is a rate.
# The explicit `unit` stops the model from prefixing an index with ₹.
MARKET_TICKERS = [
    ("^NSEI", "NIFTY 50", "points"),
    ("^BSESN", "BSE Sensex", "points"),
    ("GC=F", "Gold", "usd_per_troy_oz"),
    ("INR=X", "USD/INR", "inr_per_usd"),
]


def tool_market_indices(supabase: Client, user_id: str) -> Dict:
    """Live market snapshot — indices, gold, USD/INR. Fetched via the same
    yfinance service the Portfolio page uses (per-day cached, never throws);
    degrades to no_data when offline so the chat never crashes on market talk."""
    indices = []
    for ticker, name, unit in MARKET_TICKERS:
        p = live_price(ticker)
        if p:
            indices.append({"name": name, "ticker": ticker, "unit": unit,
                            "price": p["price"], "as_of": p["as_of"]})
    return {
        "status": "ok" if indices else "no_data",
        "indices": indices,
        "note": ("Prices are live market quotes from Yahoo Finance. "
                 "NIFTY/Sensex are index POINTS (not currency); gold is USD per "
                 "troy ounce; USD/INR is the exchange rate. Reference prices, "
                 "not buy/sell quotes."),
    }


def tool_affordability_checker(supabase: Client, user_id: str) -> Dict:
    """Answer 'Can I afford X?' — computes safe-to-spend from the user's
    real cash-flow and net-worth data (same engines as the dashboard)."""
    # Net worth (liquid + investments − liabilities)
    nw_svc = get_networth_service(supabase)
    try:
        nw = nw_svc.compute_networth(user_id)
        net_worth = nw["net_worth"]
        liquid = nw["liquid_assets"]
    except Exception:
        net_worth = liquid = 0.0

    # Monthly spending (average over last 3 months)
    try:
        db = get_db_service(supabase)
        exp = db.get_historical_expenses(user_id, months_back=3)
        if not exp.empty:
            avg_monthly = float(exp["amount"].mean())
        else:
            avg_monthly = 0.0
    except Exception:
        avg_monthly = 0.0

    # Safe-to-spend daily: (monthly_budget − spent) ÷ days left
    try:
        accounts = db.get_user_accounts(user_id)
        monthly_budget = sum(float(acc.get("monthly_budget") or 0)
                             for acc in accounts)
        spent = float(exp[exp["type"] == "Expense"]["amount"].sum()) if not exp.empty else 0.0
        remaining = max(0.0, monthly_budget - spent)
        from datetime import datetime
        now = datetime.now()
        days_in_month = (now.replace(month=now.month % 12 + 1, day=1)
                         - datetime(now.year, now.month, 1)).days
        days_left = max(1, days_in_month - now.day)
        safe_daily = remaining / days_left
    except Exception:
        safe_daily = 0.0
        remaining = 0.0
        days_left = 30

    return {
        "status": "ok",
        "net_worth": net_worth,
        "liquid_assets": liquid,
        "avg_monthly_expense": avg_monthly,
        "remaining_budget": remaining,
        "safe_to_spend_daily": round(safe_daily, 2),
        "days_left_in_month": days_left,
    }


def tool_portfolio_scorecard(supabase: Client, user_id: str) -> Dict:
    """Portfolio concentration + benchmark comparison for the AI CFO
    scorecard intent."""
    pf_svc = get_portfolio_service(supabase)
    try:
        summary = pf_svc.get_summary(user_id)
        health, insights = pf_svc.get_health(user_id, "Moderate")
    except Exception:
        return {"status": "no_data",
                "note": "No portfolio data yet — add holdings in Portfolio."}

    # Concentration: % in single holding (largest)
    allocation = summary.get("allocation", {})
    largest_class = max(allocation.items(), key=lambda kv: kv[1]) \
        if allocation else ("—", 0.0)
    concentration_pct = largest_class[1]

    # Benchmark comparison: XIRR vs Nifty 50 (yfinance)
    xirr_pct = summary.get("xirr_pct", 0.0)
    try:
        from services.market_data_service import live_price
        nifty = live_price("^NSEI")
        nifty_price = nifty["price"] if nifty else None
    except Exception:
        nifty_price = None

    return {
        "status": "ok",
        "total_invested": summary.get("total_invested", 0.0),
        "total_current": summary.get("total_current", 0.0),
        "absolute_return": summary.get("absolute_return", 0.0),
        "return_pct": summary.get("return_pct", 0.0),
        "xirr_pct": xirr_pct,
        "allocation": allocation,
        "health_score": health,
        "health_insights": insights,
        "concentration_pct": concentration_pct,
        "largest_holding": largest_class[0],
        "nifty_price": nifty_price,
    }


def tool_stock_lookup(supabase: Client, user_id: str) -> Dict:
    """Live stock/quote lookup — uses the same yfinance service as
    Portfolio. Returns the price and cross-references the user's
    holdings so the AI can say 'you already own this'."""
    from services.market_data_service import live_price
    from services.portfolio_service import get_portfolio_service

    # Resolve ticker from the user's question is handled by the router;
    # here we just return the latest price for the requested ticker(s).
    # The chat page passes the ticker as a tool argument; this tool
    # serves as the canonical data source the AI cites.
    pf_svc = get_portfolio_service(supabase)
    holdings: list[dict] = []
    try:
        holdings = pf_svc.get_holdings(user_id)
    except Exception:
        pass

    # Build a ticker→holding map for cross-reference
    holding_map: dict[str, dict] = {}
    for h in holdings:
        ticker = (h.get("ticker") or "").strip().upper()
        if ticker:
            holding_map[ticker] = h

    return {
        "status": "ok",
        "holdings": holdings,
        "holding_tickers": list(holding_map.keys()),
        "note": ("Prices are live quotes from Yahoo Finance. "
                 "cross-reference your holdings above. "
                 "Call tool_stock_lookup with the ticker to get its price."),
    }


def tool_general_knowledge(supabase: Client, user_id: str) -> Dict:
    """General knowledge fallback — checks local lesson content first,
    then degrades to a Tavily web search (same key pattern as
    insurance_search.py)."""
    # 1. Check local lessons (read-only JSON under backend/data/lessons/)
    try:
        from pathlib import Path
        lessons_dir = Path(__file__).resolve().parent.parent / "backend" / "data" / "lessons"
        if lessons_dir.exists():
            lesson_files = sorted(lessons_dir.glob("*.json")) + sorted(lessons_dir.glob("*.md"))
            if lesson_files:
                topics = [f.stem for f in lesson_files]
                return {
                    "status": "ok",
                    "source": "local_lessons",
                    "topics": topics,
                    "note": ("These topics have local lessons — the AI will cite the "
                             "matching one. If the question isn't covered, falls back "
                             "to Tavily web search."),
                }
    except Exception:
        pass

    # 2. Fallback to Tavily (same key + HTTP path as insurance_search)
    try:
        from services.insurance_search import search_web_text
        web_result = search_web_text("financial literacy", count=3)
        if web_result:
            return {
                "status": "ok",
                "source": "tavily",
                "snippets": web_result[:300],  # truncate for prompt
            }
    except Exception:
        pass

    return {
        "status": "no_data",
        "note": ("No local lesson or web result found. "
                 "Ask about a specific topic like 'XIRR', 'HRA', 'SWR', etc."),
    }


TOOL_REGISTRY: Dict[str, Tuple[str, Callable]] = {
    "tax_calculator": ("Income-tax comparison (old vs new regime)",
                       tool_tax_calculator),
    "tax_saving_opportunities": ("Deterministic tax-saving gaps",
                                 tool_tax_saving_opportunities),
    "portfolio_summary": ("Investment portfolio summary", tool_portfolio_summary),
    "net_worth": ("Net worth / balance sheet", tool_net_worth),
    "fire_status": ("FIRE (retirement) readiness", tool_fire_status),
    "spending_summary": ("Recent monthly spending", tool_spending_summary),
    "market_indices": ("Live market snapshot (indices, gold, FX)",
                       tool_market_indices),
    "affordability_checker": ("Affordability calculator", tool_affordability_checker),
    "portfolio_scorecard":  ("Portfolio scorecard", tool_portfolio_scorecard),
    "stock_lookup":         ("Live stock / quote lookup", tool_stock_lookup),
    "general_knowledge":    ("General knowledge (local lessons + Tavily)",
                             tool_general_knowledge),
}


def run_tools(supabase: Client, user_id: str,
              tool_names: List[str]) -> Dict[str, Dict]:
    """Execute the requested tools and return {name: result}."""
    out: Dict[str, Dict] = {}
    for name in tool_names:
        fn = TOOL_REGISTRY.get(name)
        if fn:
            try:
                out[name] = fn[1](supabase, user_id)
            except Exception as e:
                out[name] = {"status": "error", "error": str(e)}
    return out


def build_grounding(supabase: Client, user_id: str,
                    tool_names: List[str]) -> str:
    """Serialized grounding JSON for the chatbot prompt (the AI's only data)."""
    results = run_tools(supabase, user_id, tool_names)
    return serialize_results(results)


def serialize_results(results: Dict[str, Dict]) -> str:
    """JSON-serialize an already-built tool-results dict for the prompt.

    Stored-INR money amounts are re-expressed in the user's display currency
    (identity when INR), and a `settings` block is appended so the model always
    knows the currency, its symbol and the user's persona.
    """
    out = {name: _in_display_currency(name, data)
           for name, data in (results or {}).items()}
    out["settings"] = _user_settings()
    return _pprune(out)