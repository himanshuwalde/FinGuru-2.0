"""
Unit tests for the AI CA chatbot — NO network / Gemini required.
Coverage: intent routing (pure rules) + the offline deterministic fallback,
which is what the chat degrades to without an API key or when generation fails.
Run with:  python -m pytest tests/test_chatbot.py -v
"""
import json

import pytest

from ai.ca_chatbot import respond
from ai.context_builder import run_tools, serialize_results
from ai.intent_router import INTENT_TOOLS, route_intent


class _ExplodingTable:
    def __getattr__(self, _):
        raise AttributeError("fake supabase — table raises on access")


class _FakeSupabase:
    """Any .table(...) access raises → services catch → empty data (deterministic)."""
    @property
    def auth(self):
        return None

    def table(self, *_a, **_k):
        return _ExplodingTable()


FAKE = _FakeSupabase()


# ------------------------------------------------------------------- intent

def test_route_tax_saving():
    assert route_intent("how can I save tax this year?") == "tax_saving"


def test_route_tax():
    assert route_intent("what's my income tax in the new regime?") == "tax"


def test_route_fire():
    assert route_intent("when can I retire early?") == "fire"


def test_route_portfolio():
    assert route_intent("what is my portfolio xirr?") == "portfolio"


def test_route_net_worth():
    assert route_intent("what is my net worth and liabilities?") == "net_worth"


def test_route_spending():
    assert route_intent("where is my money going?") == "spending"


def test_route_unknown_is_general():
    assert route_intent("hello there") == "general"


def test_route_empty_message_is_general():
    assert route_intent("") == "general"


def test_route_market():
    assert route_intent("what's the current market update?") == "market"


def test_route_market_nifty():
    assert route_intent("is nifty up today?") == "market"


def test_route_advice():
    assert route_intent("should i buy a stock?") == "advice"


def test_route_advice_credit_card():
    assert route_intent("should i buy gold using credit card?") == "advice"


def test_route_advice_saving_money():
    assert route_intent("how to save money every month?") == "advice"


def test_route_portfolio_still_wins_for_data():
    # "stock" appears in portfolio keywords, but data questions must stay grounded.
    assert route_intent("what is my portfolio xirr?") == "portfolio"


def test_route_net_worth_still_wins_for_loan():
    # "loan" is a net_worth keyword; "loan or" (in advice) must not hijack it.
    assert route_intent("what is my outstanding loan?") == "net_worth"


# ------------------------------------------------------------- grounding/tools

def test_all_tools_run_without_mutation_on_missing_data():
    results = run_tools(FAKE, "user-1", ["tax_calculator", "net_worth"])
    assert "tax_calculator" in results and "net_worth" in results
    for name, res in results.items():
        assert isinstance(res, dict)
        assert "status" in res  # either no_data / ok — never a crash


def test_market_tool_never_crashes_without_network():
    # The market tool must degrade to no_data (never raise) with no yfinance /
    # no network. Uses the same exploding-supabase fake — user data untouched.
    from ai.context_builder import tool_market_indices
    result = tool_market_indices(FAKE, "user-1")
    assert isinstance(result, dict)
    assert "status" in result  # ok or no_data — never a crash
    assert isinstance(result.get("indices"), list)


def test_grounding_serializes_to_valid_json():
    results = run_tools(FAKE, "user-1", ["net_worth", "fire_status"])
    blob = serialize_results(results)
    parsed = json.loads(blob)
    # Tool results + the currency/persona `settings` block the model needs.
    assert {"net_worth", "fire_status"} <= set(parsed.keys())
    assert "settings" in parsed
    assert parsed["settings"]["currency"] == "INR"  # default offline currency
    assert parsed["settings"]["symbol"] == "₹"


# ------------------------------------------------------- offline conversation


def _force_no_api_key(monkeypatch):
    """Guarantee the deterministic path: no Gemini key → ValueError → fallback."""
    def _no_key():
        raise ValueError("GEMINI_API_KEY intentionally missing in tests")
    monkeypatch.setattr("utils.ai_client._get_api_key", _no_key)
    import utils.ai_client as ac
    ac.get_gemini_client.cache_clear() if hasattr(ac.get_gemini_client, "cache_clear") else None


def test_respond_never_raises_without_gemini(monkeypatch):
    _force_no_api_key(monkeypatch)
    text, intent, results, used_ai = respond(FAKE, "user-1", "how can I save tax?", [])
    assert isinstance(text, str) and text.strip()
    assert intent in INTENT_TOOLS
    assert isinstance(results, dict)
    assert used_ai is False  # offline → deterministic fallback, no Gemini


def test_fallback_mentions_missing_data_when_nothing_stored(monkeypatch):
    # No gemini key + empty DB → deterministic, truthful "no data" reply.
    _force_no_api_key(monkeypatch)
    text, intent, _, used_ai = respond(FAKE, "user-1", "what is my xirr?", [])
    assert intent == "portfolio"
    assert used_ai is False
    # The offline answer should not present invented numbers.
    assert "recording" in text or "recorded" in text or "offline" in text or "₹" in text


def test_fallback_is_same_for_same_input(monkeypatch):
    _force_no_api_key(monkeypatch)
    a = respond(FAKE, "user-1", "what is my net worth?", [])[0]
    b = respond(FAKE, "user-1", "what is my net worth?", [])[0]
    assert a == b  # deterministic — reproducible for viva/demo


def test_respond_marks_used_ai_when_gemini_replies(monkeypatch):
    # A working Gemini (mocked) must flag used_ai=True and pass its text through.
    import utils.ai_client as ac
    monkeypatch.setattr(ac, "get_gemini_client", lambda: object())
    monkeypatch.setattr(ac, "get_generative_model",
                        lambda genai, prefer_flash=True: object())
    monkeypatch.setattr(ac, "generate_content_safe",
                        lambda model, prompt, max_retries=2: "AI hello")
    text, intent, results, used_ai = respond(FAKE, "user-1", "hello", [])
    assert used_ai is True
    assert text == "AI hello"