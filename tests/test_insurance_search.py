"""
Unit tests for the insurance web-search module — NO network / Tavily key
required. Coverage: key lookup, Tavily JSON parsing (with a canned response),
the "never invent a premium" parser, profile-shaped queries, cover sizing with
holdings & liabilities, and deterministic per-user ranking. Mirrors
test_fire.py / test_chatbot.py style: everything pure, no live HTTP.
Run with:  python -m pytest tests/test_insurance_search.py -v
"""
import os
import json

import pytest

import services.insurance_search as ins


# ------------------------------------------------------------------- key

import streamlit as st  # test-only import — lets us stub out st.secrets below


class _EmptySecrets:
    """Stand-in for st.secrets returning nothing — keeps these tests honest
    even when the developer has a real TAVILY_API_KEY in .streamlit/secrets.toml."""

    def get(self, key, default=None):
        return default


def _clear_key_env(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)


def _no_secrets(monkeypatch):
    """Clear both env vars AND stub st.secrets so no real key can leak in."""
    _clear_key_env(monkeypatch)
    monkeypatch.setattr(st, "secrets", _EmptySecrets())


def test_get_search_key_missing_is_none(monkeypatch):
    _no_secrets(monkeypatch)
    assert ins.get_search_key() is None


def test_get_search_key_reads_env(monkeypatch):
    _no_secrets(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly_test")
    assert ins.get_search_key() == "tvly_test"


def test_get_search_key_falls_back_to_legacy_brave(monkeypatch):
    _no_secrets(monkeypatch)
    monkeypatch.setenv("BRAVE_API_KEY", "bsa_legacy")
    assert ins.get_search_key() == "bsa_legacy"


# ------------------------------------------------------------------- HTTP (mocked)

def test_get_results_never_throws_when_network_fails(monkeypatch):
    def _boom(*_a, **_k):
        raise OSError("network unreachable")
    monkeypatch.setattr("urllib.request.urlopen", _boom)
    assert ins._get_results("bsa_test", "term plans") == []


def test_get_results_never_throws_on_rate_limit(monkeypatch):
    class _429:
        def __enter__(self):
            raise Exception("429 Too Many Requests")
        def __exit__(self, *_a):
            return False
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _429())
    assert ins._get_results("bsa_test", "term plans") == []


def test_get_results_parses_tavily_json(monkeypatch):
    payload = {"results": [
        {"title": "Best Term Insurance 2026 | HDFC Life",
         "url": "https://example.com/hdfc-term",
         "content": "Compare top term plans",
         "published_date": "2026-08-12",
         "score": 0.98},
        "this entry is not a dict - ignored",
    ]}
    class _Resp:
        def __enter__(self):
            return self
        def __exit__(self, *_a):
            return False
        def read(self):
            return json.dumps(payload).encode("utf-8")

    def _fake_open(req, **_k):
        # The request must carry the Tavily bearer token.
        assert req.has_header("Authorization")
        assert req.get_header("Authorization") == "Bearer tvly_test"
        # Reject country as an ISO code — Tavily HTTP-400s on "in" (regression
        # guard: the app once sent country="in" and every search silently died).
        # Docs require full lowercase country names + the `language` param name.
        body = json.loads(req.data.decode("utf-8"))
        assert body["country"] == "india", body["country"]
        assert body["language"] == "en", body.get("language")
        assert "search_lang" not in body, body
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_open)
    results = ins._get_results("tvly_test", "term plans")
    assert len(results) == 1               # non-dict entries filtered out
    assert results[0]["title"] == "Best Term Insurance 2026 | HDFC Life"
    assert results[0]["url"] == "https://example.com/hdfc-term"


def test_parse_result_maps_tavily_fields():
    r = ins._parse_result({
        "title": "Top Term Plans | PolicyBazaar",
        "url": "https://www.policybazaar.com/term",
        "content": "Compare 2026 term plans starting from ₹500/month.\n"
                   "Renewal benefits included.",
        "published_date": "2026-08-12T10:00:00Z",
    })
    assert r["name"] == "Top Term Plans"
    assert r["provider"] == "www.policybazaar.com"   # no known-insurer token → host
    assert "₹500/month" in r["snippet"]               # multi-line content collapsed
    assert r["page_age"] == "2026-08-12"
    assert r["premium"] == "₹500/mo"                  # parsed, never invented


# ------------------------------------------------------------------- premium parsing

def test_extract_premium_inr():
    assert ins.extract_premium("premium ₹ 1,150/month") == "₹1,150/mo"
    assert ins.extract_premium("just Rs. 1,500 per year") == "₹1,500/yr"
    assert ins.extract_premium("₹10,000/yr coverage") == "₹10,000/yr"
    assert ins.extract_premium("premium of ₹1,150.60 monthly") == "₹1,151/mo"


def test_extract_premium_never_invents():
    # Sum insured, not a premium → None. Never present a figure as a price.
    assert ins.extract_premium("₹1 Crore term cover for just 5,000") is None
    # No period qualifier → not a recurring cost we can vouch for → None.
    assert ins.extract_premium("low premiums from just ₹500") is None
    assert ins.extract_premium("no amount at all here") is None
    assert ins.extract_premium("") is None


# ------------------------------------------------------------------- queries

def test_build_query_uses_profile():
    family = ins.build_query("term", {"dependents": 2, "smoker": False})
    assert "family" in family and "term life insurance" in family
    solo = ins.build_query("term", {"dependents": 0, "smoker": False})
    assert "family" not in solo

    fl = ins.build_query("health", {"dependents": 3, "smoker": False})
    assert "family floater" in fl
    diag = ins.build_query("health", {"dependents": 0, "smoker": True})
    assert "diabetes care" in diag
    assert "family floater" not in diag


def test_search_policies_without_key_returns_empty():
    assert ins.search_policies("", {}) == {"term": [], "health": []}


# ------------------------------------------------------------------- cover sizing

def test_recommend_term_cover_adds_liabilities_deducts_assets():
    cover, note = ins.recommend_term_cover(
        annual_income=12_00_000, dependents=2, existing_cover=0,
        net_worth={"liquid_assets": 5_00_000, "investments_total": 5_00_000,
                   "total_liabilities": 20_00_000, "liabilities_breakdown": []})
    # 15+2 = ×17 → 2,04,00,000 + 20,00,000 − 10,00,000 = 2,14,00,000
    assert cover == 2_14_00_000
    assert note == ""


def test_recommend_term_cover_deducts_existing_cover():
    cover, _ = ins.recommend_term_cover(
        10_00_000, 0, existing_cover=50_00_000,
        net_worth={"liquid_assets": 0, "investments_total": 0,
                   "total_liabilities": 0, "liabilities_breakdown": []})
    assert cover == 1_00_00_000           # 15×10L − 50L = 1Cr


def test_recommend_term_cover_floors_at_5l():
    # Assets alone cover the gap → floor, plus an honest note (no invented math).
    cover, note = ins.recommend_term_cover(
        10_00_000, 1, existing_cover=0,
        net_worth={"liquid_assets": 2_00_00_000, "investments_total": 0,
                   "total_liabilities": 0, "liabilities_breakdown": []})
    assert cover == 5_00_000
    assert "assets" in note


def test_recommend_health_cover_scales_with_family():
    solo = ins.recommend_health_cover(0, metro=True, existing_cover=0)
    family = ins.recommend_health_cover(3, metro=True, existing_cover=0)
    assert solo == 25_00_000
    assert family == 40_00_000            # 25L + 3×5L


# ------------------------------------------------------------------- ranking

def _candidate(title, premium=None, snippet=""):
    return {"title": title, "snippet": snippet, "premium": premium,
            "name": title, "provider": "X", "url": "https://x.in"}


def test_rank_term_prefers_critical_illness_for_smoker():
    profile = {"smoker": True, "dependents": 0, "annual_income": 12_00_000}
    plain = _candidate("Max Life Smart Secure", snippet="pure protection")
    ci = _candidate("ICICI iProtect Smart", snippet="critical illness cover included")
    ranked = ins.rank_policies([plain, ci], profile, "term", top_n=3)
    assert ranked[0]["title"] == ci["title"]


def test_rank_health_prefers_family_for_dependents():
    profile = {"smoker": False, "dependents": 3, "annual_income": 12_00_000,
               "age": 32}
    solo = _candidate("Individual Health Plan", snippet="for one person")
    fam = _candidate("Family Floater", snippet="family floater cover")
    ranked = ins.rank_policies([solo, fam], profile, "health", top_n=3)
    assert ranked[0]["title"] == fam["title"]


def test_rank_prefers_candidate_with_visible_premium():
    profile = {"smoker": False, "dependents": 0, "annual_income": 12_00_000,
               "age": 32}
    no_price = _candidate("Basic Plan", snippet="lowest premium plans")
    priced = _candidate("Priced Plan", premium="₹1,150/mo",
                        snippet="costs ₹1,150 per month")
    ranked = ins.rank_policies([no_price, priced], profile, "health", top_n=3)
    assert ranked[0]["title"] == priced["title"]   # same signal, premium tiebreak


def test_rank_limits_to_top_n():
    profile = {"smoker": False, "dependents": 0, "annual_income": 12_00_000,
               "age": 32}
    cands = [_candidate(f"Plan {i}") for i in range(6)]
    assert len(ins.rank_policies(cands, profile, "term", top_n=3)) == 3