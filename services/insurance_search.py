"""
Insurance web search — Tavily Search API.

Fetches the *latest* Indian term-life and health insurance plans in real time
and scores them against a user's profile (age, dependents, smoker, income).
Everything follows the app's never-throw contract:

- `get_search_key()` returns None when no TAVILY_API_KEY is configured → the
  page degrades to its curated market database.
- `_get_results()` swallows every network / auth / rate-limit error and returns
  [] so the page never crashes when Tavily is down.
- Premiums are surfaced ONLY when a result's snippet itself contains an
  Indian-rupee figure with a period ("₹1,150/month", "Rs. 1,500/yr").
  They are parsed, never invented — a snippet without a price yields None.

Why Tavily: DuckDuckGo's free endpoint (probed live) mangles category queries
like "best term life insurance plans India" into dictionary hits and rate-limits
cloud IPs. Tavily is free (1,000 credits/month) yet returns clean web-search
JSON (title, url, content, published_date) through the same lazy-secrets key
pattern the old Brave integration used.

No top-level `import streamlit`: takes the lazy `st.secrets` approach of
`utils/currency.py` so the module stays importable under plain pytest.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date
from typing import Dict, List, Optional, Tuple

_TAVILY_URL = "https://api.tavily.com/search"

# ₹ amounts only count as a "premium" when a period follows within the same
# phrase ("/month", "per year", "annually", "p.a."). A bare "₹1 Crore cover"
# (sum insured) or an unqualified ₹ figure is ignored — we surface only what the
# snippet clearly states is a recurring cost. Conservative on purpose.
_PREMIUM_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s?([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*"
    r"(per\s+month|per\s+year|per\s+annum|monthly|annually|"
    r"/\s*mo(?:nth)?\b|/\s*yr(?:ear)?\b|y/?r\b|p\.?\s*a\.?\b)",
    re.IGNORECASE,
)

# (lowercase token, canonical display name). Longer tokens first in matching so
# "max life" wins over plain "max", "niva bupa" over "bupa", "care health" over
# a bare "care". Provider extraction is best-effort — used only for the card
# caption; the result's source site is the fallback.
_INSURERS: List[Tuple[str, str]] = [
    ("aditya birla", "Aditya Birla Health"),
    ("future generali", "Future Generali"),
    ("manipal cigna", "ManipalCigna"),
    ("manipalcigna", "ManipalCigna"),
    ("care health", "Care Health"),
    ("niva bupa", "Niva Bupa"),
    ("max life", "Max Life"),
    ("hdfc", "HDFC"),
    ("icici", "ICICI"),
    ("bajaj", "Bajaj Allianz"),
    ("bandhan", "Bandhan Life"),
    ("reliance", "Reliance"),
    ("edelweiss", "Edelweiss"),
    ("kotak", "Kotak"),
    ("sbi", "SBI"),
    ("tata", "Tata"),
    ("lic", "LIC"),
    ("bupa", "Bupa"),
    ("cigna", "Cigna"),
    ("star", "Star Health"),
    ("digit", "Digit"),
    ("acko", "Acko"),
    ("docprime", "DocPrime"),
    ("navi", "Navi"),
]


# ---------------------------------------------------------------- key

def get_search_key() -> Optional[str]:
    """Tavily API key from env → Streamlit secrets. Falls back to a legacy
    BRAVE_API_KEY so existing deployments keep working. None when unset
    (never raises)."""
    for name in ("TAVILY_API_KEY", "BRAVE_API_KEY"):
        key = os.environ.get(name)
        if key:
            return key
        try:
            import streamlit as st  # lazy — keeps this module pytest-clean
            if hasattr(st, "secrets"):
                key = st.secrets.get(name)
                if key:
                    return key
        except Exception:
            pass
    return None


def search_web_text(query: str, count: int = 5) -> str:
    """Run one Tavily query and return joined 'Title — snippet' text.

    Generic companion to the insurance helpers: other services (FIRE's live
    inflation lookup) reuse the same key + HTTP path instead of each building
    its own web-search client. Returns '' on any failure (never raises) —
    callers degrade to their own fallbacks.
    """
    key = get_search_key()
    if not key:
        return ""
    chunks = []
    for r in _get_results(key, query, count=count):
        title = str(r.get("title") or "").strip()
        content = " ".join(str(r.get("content") or "").split())
        if title or content:
            chunks.append(f"{title} — {content}")
    return "\n".join(chunks)


# ---------------------------------------------------------------- tavily http

def _get_results(key: str, query: str, count: int = 10) -> List[Dict]:
    """Run one Tavily web search (India, English, past year). Returns [] on any
    failure — HTTP error, 429 rate-limit, network down, unparsable JSON."""
    payload = {
        "query": query,
        "max_results": count,
        "search_depth": "basic",
        "topic": "general",
        "days": 365,                     # past-year freshness = "latest"
        "country": "india",              # full lowercase name — Tavily rejects ISO codes (HTTP 400)
        "language": "en",                # ISO-639-1; boosts English results
        "include_answer": False,
        "include_raw_content": False,
    }
    req = urllib.request.Request(
        _TAVILY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        results = ((body or {}).get("results")) or []
        return [r for r in results if isinstance(r, dict)]
    except Exception as e:
        print(f"[insurance_search] Tavily search failed: {e}")
        return []


# ---------------------------------------------------------------- parsing

def extract_premium(text: str) -> Optional[str]:
    """Normalize the first INR-with-period figure in `text` to '₹X,XXX/mo' or
    '/yr'. None when the text has no such figure (never invent a price)."""
    m = _PREMIUM_RE.search(text or "")
    if not m:
        return None
    amount = m.group(1).replace(",", "")
    period = (m.group(2) or "").lower()
    try:
        amt = int(round(float(amount)))
    except ValueError:
        return None
    monthly = "month" in period or "monthly" in period
    return f"₹{amt:,}/mo" if monthly else f"₹{amt:,}/yr"


def _host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc
    except Exception:
        return ""


def extract_provider(title: str) -> Optional[str]:
    """Known insurer found in a result title (longest token wins), else None."""
    low = (title or "").lower()
    for token, canonical in sorted(_INSURERS, key=lambda t: len(t[0]), reverse=True):
        if re.search(rf"\b{re.escape(token)}\b", low):
            return canonical
    return None


def _clean_name(title: str) -> str:
    """Strip the '| PolicyBazaar' / ' - MoneyControl' tail off an article title."""
    out = (title or "").strip()
    for sep in (" | ", " |", " – ", " - "):
        if sep in out:
            out = out.split(sep, 1)[0].strip()
    return out


def _parse_result(r: Dict) -> Dict:
    title = str(r.get("title") or "").strip()
    content = str(r.get("content") or "").strip()
    # Tavily returns multi-line content; join collapsed to a single snippet.
    snippet = " ".join(x.strip() for x in content.splitlines() if x.strip())
    source = _host(r.get("url") or "")
    page_age = r.get("published_date") or r.get("age") or ""
    return {
        "name": _clean_name(title) or title,
        "provider": extract_provider(title) or source,
        "title": title,
        "snippet": snippet or content,
        "url": str(r.get("url") or "").strip(),
        "source": source,
        "page_age": str(page_age)[:10] if page_age else "",
        "premium": extract_premium(snippet),
    }


# ---------------------------------------------------------------- queries

def build_query(category: str, profile: Dict, year: Optional[int] = None) -> str:
    """One search query per category, shaped by the user's profile so the top
    results already lean toward their situation."""
    year = year or date.today().year
    if category == "term":
        q = f"best term life insurance plans India {year}"
        if int(profile.get("dependents") or 0) > 0:
            q += " for family"
        if profile.get("smoker"):
            q += " smoker friendly"
        return q
    q = f"best health insurance plans India {year}"
    if int(profile.get("dependents") or 0) > 0:
        q += " family floater"
    if profile.get("smoker"):
        q += " diabetes care"
    return q


def search_policies(key: str, profile: Dict) -> Dict[str, List[Dict]]:
    """Search term-life + health in real time, return parsed candidates
    {name, title, snippet, url, source, page_age, provider, premium}.
    {"term": [], "health": []} when there's no key or a search fails."""
    out: Dict[str, List[Dict]] = {"term": [], "health": []}
    if not key:
        return out
    for category in ("term", "health"):
        raw = _get_results(key, build_query(category, profile))
        out[category] = [_parse_result(r) for r in raw if (r or {}).get("title")]
    return out


# ---------------------------------------------------------------- ranking

def _score_one(c: Dict, profile: Dict, category: str) -> int:
    """Lower is better. Keyword signals over title+snippet — deterministic, no
    LLM, never invents numbers."""
    text = f'{c.get("title") or ""} {c.get("snippet") or ""}'.lower()
    score = 0
    if category == "term":
        if profile.get("smoker") and "critical illness" in text:
            score -= 2                       # CI payout is extra valuable to smokers
        if "return of premium" in text:
            score -= 1
        if "accident" in text and "waiver" in text:
            score -= 1
        if float(profile.get("annual_income") or 0) < 5_00_000 and any(
                k in text for k in ("low premium", "cheapest", "best value",
                                    "lowest premium", "affordable")):
            score -= 2                       # low-income users need max cover per rupee
    else:  # health
        if int(profile.get("dependents") or 0) > 0 and any(
                k in text for k in ("family", "floater")):
            score -= 2
        if int(profile.get("dependents") or 0) == 0 and any(
                k in text for k in ("individual", "solo", "single")):
            score -= 1
        if profile.get("smoker") and any(
                k in text for k in ("diabetes", "pre-existing", "chronic")):
            score -= 2
        if int(profile.get("age") or 30) >= 45 and any(
                k in text for k in ("pre-existing", "chronic", "senior")):
            score -= 2
        if any(k in text for k in ("no sub-limit", "no room rent", "restore")):
            score -= 1
        if any(k in text for k in ("newborn", "maternity")) and \
                int(profile.get("age") or 30) <= 35 and \
                int(profile.get("dependents") or 0) > 0:
            score -= 1
    return score


def rank_policies(candidates: List[Dict], profile: Dict, category: str,
                  top_n: int = 3) -> List[Dict]:
    """Sort candidates by signal score (lower better); among equal signals, a
    candidate whose snippet shows a real premium ranks first (more concrete)."""
    def _key(c: Dict) -> Tuple[int, int]:
        return (_score_one(c, profile, category), 0 if c.get("premium") else 1)
    ranked = sorted((c for c in candidates if c), key=_key)
    return [dict(c) for c in ranked[:top_n]]


# ------------------------------------------------------------ cover sizing

def recommend_term_cover(annual_income: float, dependents: int,
                         existing_cover: float,
                         net_worth: Optional[Dict] = None) -> Tuple[int, str]:
    """Human-life-value cover + clearing the user's actual debts − their real
    financial assets (bank balances + investments) − existing cover. Floor
    ₹5,00,000. Returns (cover, note); `note` explains when assets alone already
    close the gap."""
    nw = net_worth or {}
    multiplier = 15 + min(int(dependents or 0), 5)
    liabilities = float(nw.get("total_liabilities") or 0)
    assets = (float(nw.get("liquid_assets") or 0)
              + float(nw.get("investments_total") or 0))
    raw = annual_income * multiplier + liabilities - assets - float(existing_cover or 0)
    cover = int(max(5_00_000, round(raw, -5)))
    note = ""
    if raw <= 5_00_000:
        note = ("Your financial assets already cover the income-replacement and "
                "debt gap — the floor of ₹5,00,000 just handles final expenses.")
    return cover, note


def recommend_health_cover(dependents: int, metro: bool,
                           existing_cover: float) -> int:
    """Recommended health cover in ₹ — medical needs scale with family and
    city, not with debts, so liabilities don't enter here."""
    base = 25_00_000 if metro else 15_00_000
    dep_add = int(dependents or 0) * 5_00_000
    raw = base + dep_add - float(existing_cover or 0)
    return int(max(5_00_000, round(raw, -5)))