"""AI CFO router — grounded chat, affordability, portfolio scorecard, stock lookup,
general knowledge, and score-explanation endpoints. Every reply is built from
deterministic engine outputs (never invents a number)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.auth.dependencies import AuthContext, get_auth_context
from backend.schemas.common import PillarStatus, SuccessBody
from backend.supabase_client import SupabaseNotConfigured, user_client
from services.database import get_db_service
from services.market_data_service import live_price

from ai.context_builder import (
    run_tools,
    serialize_results,
)
from ai.intent_router import INTENT_TOOLS, route_intent
from ai.prompts import build_prompt, deterministic_answer
from ai.ca_chatbot import respond as ca_respond

router = APIRouter(prefix="/ai-cfo", tags=["ai-cfo"])

_MODULES = [
    "grounded_chat",
    "affordability_queries",
    "portfolio_scorecard",
    "stock_lookup",
    "general_knowledge",
    "explain_score_panel",
    "chat_sessions",
]


# ── DTOs ──────────────────────────────────────────────────────────────────
class ChatIn(BaseModel):
    user_message: str

class AffordabilityIn(BaseModel):
    amount: float

class StockIn(BaseModel):
    ticker: str

class GeneralIn(BaseModel):
    question: str


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_client(auth: AuthContext):
    try:
        return user_client(auth.access_token)
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail="Database backend is not configured") from exc


def _grounding(tool_names: List[str], supabase, user_id: str) -> dict:
    results = run_tools(supabase, user_id, tool_names)
    return serialize_results(results)


# ── /status ───────────────────────────────────────────────────────────────

@router.get("/status", response_model=PillarStatus)
def ai_cfo_status() -> PillarStatus:
    return PillarStatus(pillar="ai-cfo", modules=_MODULES)


# ── /chat ─────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=SuccessBody)
def ai_cfo_chat(inp: ChatIn, auth: AuthContext = Depends(get_auth_context)) -> JSONResponse:
    """Grounded AI CFO chat — Gemini explains real computed numbers."""
    supabase = _get_client(auth)
    text, intent, results, used_ai = ca_respond(
        supabase, auth.user.id, inp.user_message, history=[],
    )
    grounding = serialize_results(results)
    return JSONResponse(
        content=SuccessBody(
            response=text.strip(),
            intent=intent,
            grounding=grounding,
            used_ai=used_ai,
        ).model_dump(exclude_none=True)
    )


# ── /affordability ──────────────────────────────────────────────────────

@router.post("/affordability", response_model=SuccessBody)
def ai_cfo_affordability(inp: AffordabilityIn, auth: AuthContext = Depends(get_auth_context)) -> JSONResponse:
    """Answer 'Can I afford X?' — real cash-flow + net-worth from engines."""
    supabase = _get_client(auth)
    results = run_tools(supabase, auth.user.id, ["affordability_checker"])
    afford = results.get("affordability_checker", {})
    if afford.get("status") != "ok":
        text = "Can't compute affordability yet — add income and expenses first."
        return JSONResponse(
            content=SuccessBody(
                response=text,
                intent="affordability",
                grounding=serialize_results(results),
                used_ai=False,
            ).model_dump(exclude_none=True)
        )
    safe = afford.get("safe_to_spend_daily", 0)
    remaining = afford.get("remaining_budget", 0)
    days = afford.get("days_left_in_month", 30)
    text = (
        f"You have about ₹{safe}/day safe-to-spend "
        f"(≈ ₹{safe * days:.0f} this month; "
        f"remaining budget ₹{remaining} left, "
        f"{days} days left)."
    )
    return JSONResponse(
        content=SuccessBody(
            response=text,
            intent="affordability",
            grounding=serialize_results(results),
            used_ai=True,
        ).model_dump(exclude_none=True)
    )


# ── /portfolio-scorecard ────────────────────────────────────────────────

@router.post("/portfolio-scorecard", response_model=SuccessBody)
def ai_cfo_portfolio_scorecard(auth: AuthContext = Depends(get_auth_context)) -> JSONResponse:
    """Concentration + benchmark scores for the AI CFO portfolio card."""
    supabase = _get_client(auth)
    results = run_tools(supabase, auth.user.id, ["portfolio_scorecard"])
    scorecard = results.get("portfolio_scorecard", {})
    lines: List[str] = []
    if scorecard.get("health_score") is not None:
        hs = scorecard["health_score"]
        ins = scorecard.get("health_insights", ["—"])[0]
        lines.append(f"Health score: {hs}/100 ({ins}).")
    if scorecard.get("concentration_pct") is not None:
        lines.append(
            f"Concentration: {scorecard['concentration_pct']:.0f}% "
            f"in {scorecard.get('largest_holding', '—')}.")
    nifty = scorecard.get("nifty_price")
    if nifty:
        lines.append(f"NIFTY 50: {nifty:,.2f} pts.")
    text = " ".join(lines) if lines else "No portfolio data yet."
    return JSONResponse(
        content=SuccessBody(
            response=text,
            intent="portfolio_scorecard",
            grounding=serialize_results(results),
            used_ai=True,
        ).model_dump(exclude_none=True)
    )


# ── /stock-lookup ────────────────────────────────────────────────────────

@router.post("/stock-lookup", response_model=SuccessBody)
def ai_cfo_stock_lookup(inp: StockIn, auth: AuthContext = Depends(get_auth_context)) -> JSONResponse:
    """Live stock/quote lookup using services/market_data_service.py::live_price()."""
    supabase = _get_client(auth)
    p = live_price(inp.ticker)
    if p:
        text = f"{inp.ticker}: {p['price']:.2f} ({p['as_of']})"
    else:
        text = f"Live price unavailable for {inp.ticker} (network / yfinance off-line)."
    return JSONResponse(
        content=SuccessBody(
            response=text,
            intent="stock_lookup",
            grounding=serialize_results(run_tools(supabase, auth.user.id, ["stock_lookup"])),
            used_ai=True,
        ).model_dump(exclude_none=True)
    )


# ── /general-knowledge ──────────────────────────────────────────────────

@router.post("/general-knowledge", response_model=SuccessBody)
def ai_cfo_general_knowledge(inp: GeneralIn, auth: AuthContext = Depends(get_auth_context)) -> JSONResponse:
    """Check local lesson content first, then Tavily web search."""
    supabase = _get_client(auth)
    results = run_tools(supabase, auth.user.id, ["general_knowledge"])
    gk = results.get("general_knowledge", {})
    if gk.get("status") == "ok" and gk.get("source") == "local_lessons":
        topics = gk.get("topics", [])
        text = f"Local lesson topics: {', '.join(topics)}." if topics else "No matching lesson."
    elif gk.get("status") == "ok" and gk.get("source") == "tavily":
        text = f"Web search result: {gk.get('snippets', '')[:200]}."
    else:
        text = "No lesson or web result found. Try a specific topic like XIRR, HRA, or SWR."
    return JSONResponse(
        content=SuccessBody(
            response=text,
            intent="general_knowledge",
            grounding=serialize_results(results),
            used_ai=True,
        ).model_dump(exclude_none=True)
    )


# ── /explain-score ──────────────────────────────────────────────────────

@router.post("/explain-score", response_model=SuccessBody)
def ai_cfo_explain_score(metric: str, auth: AuthContext = Depends(get_auth_context)) -> JSONResponse:
    """Tell the user which engine function produced the cited metric."""
    tool_map: dict[str, str] = {
        "net_worth": "net_worth",
        "portfolio_value": "portfolio_summary",
        "safe_to_spend": "spending_summary",
        "tax_owed": "tax_calculator",
        "xirr": "portfolio_summary",
    }
    tool_name = tool_map.get(metric, "net_worth")
    supabase = _get_client(auth)
    try:
        results = run_tools(supabase, auth.user.id, [tool_name])
        text = f"'{metric}' is computed by the {tool_name.replace('_', ' ').title()} engine from your saved data."
        return JSONResponse(
            content=SuccessBody(
                response=text,
                intent="explain_score_panel",
                grounding=serialize_results(results),
                used_ai=True,
            ).model_dump(exclude_none=True)
        )
    except Exception:
        text = f"Can't explain '{metric}' right now — data not recorded."
        return JSONResponse(
            content=SuccessBody(
                response=text,
                intent="explain_score_panel",
                grounding={},
                used_ai=False,
            ).model_dump(exclude_none=True)
        )


# ── Tiny helper ──────────────────────────────────────────────────────────

def _fmt_money(v: float) -> str:
    from utils.currency import fmt_money
    return fmt_money(v)