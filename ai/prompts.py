"""
Prompts — the grounding contract for the CA chatbot.
The system prompt instructs Gemini to answer from the user's real computed
figures when the question concerns them, and to give general financial education
(when asked, never inventing prices or returns). All numbers in any reply are
grounded in the injected JSON or explicitly labelled as general knowledge.
"""
from __future__ import annotations

from typing import List, Dict

from utils.currency import fmt_money

SYSTEM_PROMPT = """You are **CA Guru**, FinGuru's chartered-accountant assistant. \
You explain *computed* numbers — you never compute them yourself — and you give \
general, educational financial guidance when asked.

ANSWER MODE (pick based on the user's question):

1. USER-DATA questions (tax, portfolio, net worth, FIRE, spending, investments):
   → Answer ONLY from the "GROUNDING DATA" JSON below. Every specific figure you \
   quote must appear in it.
   → If the grounding says "status": "no_data" for something, say the data isn't \
   recorded yet and tell the user where to enter it (Tax Planner / Portfolio / \
   Net Worth / FIRE Planner). Never invent numbers.
   → If you cannot answer from the grounding, say so plainly.

2. GENERAL / EDUCATIONAL questions (market trends, "should I buy", saving tips, \
payment methods, financial concepts, commodity advice):
   → You MAY answer using financial principles and decision frameworks.
   → NEVER invent specific current prices, index levels, interest rates, or \
   percentage returns that are not in the GROUNDING DATA.
   → If the grounding includes `market_indices`, you MAY quote those real figures \
   (e.g. "NIFTY 50 is at 24,500 as of 2026-09-15"). Refer to them by their `as_of` \
   date so the user knows they're live quotes, not predictions.
   → If asked for a specific stock/ETF price you don't have, say you don't have \
   that data and suggest a live source (e.g. Google Finance, NSE, Yahoo Finance).
   → When the user's own data IS relevant (e.g. "should I buy stock X" and they \
   own it), weave it into your general answer as a personalized angle — but never \
   present general guidance as figures computed for this user.

RULES (apply to all answers):
- Keep responses concise (under ~200 words), structured with short bullet points \
or lines. End with ONE actionable next step when relevant.
- Cite which part of the grounding data you're using (e.g. "Your portfolio shows…").
- General/educational answers end with a short risk note: "Markets carry risk. \
This is educational, not personalized investment advice." (For user-data answers \
this note is optional and can be omitted to stay concise.)
- If an exact figure you need is missing, work only from what IS present and say \
which assumption you made (e.g. "assumed 4% safe withdrawal rate").
"""


def build_prompt(user_message: str,
                 grounding_json: str,
                 history: List[Dict],
                 persona_block: str = "",
                 currency_note: str = "") -> str:
    """Assemble the full prompt: system rules + persona/currency + grounding +
    conversation. `persona_block` and `currency_note` are optional strict
    instructions injected before the data."""
    turns = []
    for m in history:
        turns.append(f"{m['role'].upper()}: {m['content']}")
    history_str = "\n".join(turns[-6:]) if turns else "No prior turns."

    persona_section = persona_block if persona_block.strip() else (
        "PERSONA: You are a neutral, strictly professional financial assistant.")
    currency_section = currency_note if currency_note.strip() else (
        "Use proper currency symbols/labels for every amount you mention.")

    return f"""{SYSTEM_PROMPT}

============================== PERSONA ==============================
{persona_section}

=========================== CURRENCY RULE ===========================
{currency_section}

========== GROUNDING DATA (real computed figures + live market quotes) ==========
{grounding_json}
====================================================================

CONVERSATION SO FAR:
{history_str}

USER QUESTION: {user_message}

Answer now, following the grounding rules."""


# ------------------------------------------------------------------ fallback

def deterministic_answer(intent: str, results: Dict[str, Dict]) -> str:
    """
    Offline fallback when the AI service is unavailable: build a concise,
    truthful answer straight from the engine outputs (no Gemini, no invention).
    Called by ca_chatbot when generation fails — so the chat never goes blank.
    """
    lines: List[str] = []
    net = results.get("net_worth", {})
    if net.get("status") == "ok":
        lines.append(f"Net worth: {_inr(net['net_worth'])} "
                     f"(assets {_inr(net['total_assets'])} "
                     f"− liabilities {_inr(net['total_liabilities'])}).")
    port = results.get("portfolio_summary", {})
    if port.get("status") == "ok":
        lines.append(f"Investments: {_inr(port['total_current'])} "
                     f"(+{port['return_pct']:.1f}%, XIRR {port['xirr_pct']:.1f}%).")
    spend = results.get("spending_summary", {})
    if spend.get("status") == "ok":
        lines.append(f"Average monthly spend: {_inr(spend['avg_monthly_expense'])}.")
    tax = results.get("tax_calculator", {})
    if tax.get("status") == "ok":
        lines.append(f"Recommended tax regime: {tax['recommended_regime'].upper()} "
                     f"(saving {fmt_money(tax['potential_saving'])}).")
    opp = results.get("tax_saving_opportunities", {})
    if opp.get("status") == "ok" and opp.get("opportunities"):
        lines.append("Tax-saving gaps: " + "; ".join(opp["opportunities"]))
    fire = results.get("fire_status", {})
    if fire.get("status") == "ok":
        lines.append(f"FIRE probability: {fire['probability_pct']:.0f}% "
                     f"(median corpus {_inr(fire['median_corpus'])} vs required "
                     f"{_inr(fire['required_corpus'])}).")
    # Live market snapshot — index points, gold USD/oz, FX rate. These are NOT
    # rupees so never go through _inr(); units come from the tool's `unit` field.
    _UNIT_LABEL = {"points": "pts", "usd_per_troy_oz": "USD/oz",
                   "inr_per_usd": "INR/USD"}
    market = results.get("market_indices", {})
    if market.get("status") == "ok" and market.get("indices"):
        parts = [f"{ix['name']}: {ix['price']:,.2f} "
                 f"{_UNIT_LABEL.get(ix.get('unit'), '')}".rstrip()
                 for ix in market["indices"]]
        lines.append("Market snapshot: " + ", ".join(parts) + ".")

    # --- AI CFO specific fallbacks ---
    afford = results.get("affordability_checker", {})
    if afford.get("status") == "ok":
        safe = afford.get("safe_to_spend_daily", 0)
        lines.append(f"Safe-to-spend today: {_inr(safe)} "
                     f"(budget {_inr(afford.get('remaining_budget', 0))} "
                     f"left, {afford.get('days_left_in_month', 30)} days).")

    scorecard = results.get("portfolio_scorecard", {})
    if scorecard.get("status") == "ok":
        lines.append(f"Portfolio score: {scorecard.get('health_score', '—')}/100. "
                     f"Concentration: {scorecard.get('concentration_pct', 0):.0f}% "
                     f"in {scorecard.get('largest_holding', '—')}.")
        nifty = scorecard.get("nifty_price")
        if nifty:
            lines.append(f"NIFTY 50: {nifty:,.2f} pts.")

    stock = results.get("stock_lookup", {})
    if stock.get("status") == "ok" and stock.get("holdings"):
        tickers = ", ".join(stock.get("holding_tickers", []))
        lines.append(f"Your holdings: {tickers}.")

    gk = results.get("general_knowledge", {})
    if gk.get("status") == "ok":
        topics = gk.get("topics", [])
        if topics:
            lines.append(f"Local lessons available: {', '.join(topics)}.")
        elif gk.get("source") == "tavily":
            lines.append("Web search result found — AI will cite it.")
        else:
            lines.append("No local lesson found — AI will use general knowledge.")

    if not lines:
        # General / advice / market intents give a better offline message.
        if intent in ("market", "advice", "general"):
            return ("I can give you a general framework for this question. "
                    "AI explanation is temporarily offline — for live market data "
                    "check Google Finance or NSE; for personalized advice, "
                    "please ensure AI is enabled. (General guidance requires the "
                    "AI engine.)")
        return ("I couldn't find enough recorded data to answer yet. Enter your "
                "income in Tax Planner, add investments, and save a FIRE plan "
                "first — then ask me again. (AI summary unavailable offline.)")
    return ("⚠️ AI explanation is temporarily offline — here's what the numbers "
            "say directly:\n• " + "\n• ".join(lines))


def _inr(v) -> str:
    return fmt_money(float(v))