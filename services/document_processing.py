"""Shared document-processing pipeline used by the AI Document Scanner and Bank Sync.

Implements the missing upload-workflow steps so the two pages don't drift:

  #2  pre-check              -> validate_upload()
  #3  AI extraction          -> extract_with_gemini()
  #4  schema sanity + check  -> validate_transactions() + reconcile()
  #5  dedup (app-level)      -> fingerprint() + persist_with_dedup()

Conventions (mirrored from services/insurance_search.py):
  * no top-level `import streamlit`
  * helpers NEVER raise — failures come back as None / [] / {"error": ...}
  * pure functions take inputs explicitly (name/size, model+client, supabase)
    so they are easy to unit-test with fakes.
"""
import json
import os
import re
import tempfile
from datetime import datetime

from utils.security import decrypt_data, encrypt_data
from utils.anomaly_engine import check_and_alert_anomaly

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED_EXTENSIONS = {".json", ".pdf", ".png", ".jpg", ".jpeg"}

# Sign convention: Income adds to the balance, Expense subtracts (matches the app).
_MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

_EXTRACTION_PROMPT = """You are a strict financial data extraction AI. Extract all transactions from this document.
Return ONLY a single JSON object (no markdown, no ```json fences, no intro, no outro) shaped exactly like:
{
  "opening_balance": <number or null>,
  "closing_balance": <number or null>,
  "transactions": [
    {
      "desc": (string) The counterparty or merchant ONLY — see the narration rule below.
      "amount": (float) The positive transaction amount (always positive, never negative).
      "category": (string) Choose ONE from: Food & Dining, Transport, Shopping, Entertainment, Groceries, Utilities, Income, Education, Other.
      "type": (string) "Expense" or "Income" — see the direction rule below.
      "date": (string) "YYYY-MM-DD" format. If an exact time is visible on the document, use "YYYY-MM-DD HH:MM:SS". Do NOT guess 00:00:00 if the time is missing.
    }
  ]
}

DIRECTION RULE (CRITICAL — most errors come from getting this wrong):
You MUST determine whether money is LEAVING the account (Expense) or ENTERING the account (Income) by
reading the bank statement's own columns or indicators. Look for these signals IN ORDER:
  1. Separate DEBIT / CREDIT columns: amount in the DEBIT column = "Expense"; amount in the CREDIT column = "Income".
     On Indian bank statements the DEBIT column is typically on the LEFT and CREDIT on the RIGHT.
  2. Sign or label: a minus sign, dash, or "Dr"/"DR" suffix means money LEFT the account → "Expense".
     A plus sign, no sign in a credit column, or "Cr"/"CR" means money ENTERED → "Income".
  3. Narration text direction: "Paid to", "Sent to", "Transferred to", "Debited for" → "Expense".
     "Received from", "Credited by", "Deposited by", "Refund from" → "Income".
  4. Transaction nature: salary, salary credit, interest, interest credited, refund, cashback, dividend,
     maturity payout, NEFT/IMPS/RTGS received → "Income". EVERYTHING ELSE (UPI payment, POS swipe,
     ATM withdrawal, online purchase, bill payment, EMI debit, rent, fuel, grocery purchase) → "Expense".
  **WHEN IN DOUBT, DEFAULT TO "Expense"** — it is far worse to show a debit as income than vice versa.

NARRATION RULE (very important): Indian bank statements write full UPI/IMPS/NEFT narrations like
"UPI 004478649026/YESB/SURBHI DURGESH GUPTA/Paid vi". For these, put in "desc" ONLY the
counterparty's NAME — the merchant or person — and drop all the surrounding noise:
  * drop UPI reference numbers (long digit strings) and UPI handles (digits@bank),
  * drop bank codes (YESB, HDFC, ICIC, SBI, PYTM, ...),
  * drop the leading "UPI"/"NEFT"/"IMPS"/"POS" marker,
  * drop remark tails like "Paid via", "Paid vi", "Transfer".
Example: "UPI 004478649026/YESB/SURBHI DURGESH GUPTA/Paid vi" -> "desc": "SURBHI DURGESH GUPTA".

CATEGORY RULE (strict — the app enforces these after extraction):
  * **ABSOLUTE RULE: if "type" is "Income" (money received / credited), "category" MUST be "Income".**
    No exceptions — never put an Income-type transaction in any other category.
  * Otherwise, for Expense-type transactions, pick from the merchant/person name in "desc":
    - a known restaurant/food brand (Zomato, Swiggy, KFC, Domino's, a cafe, a restaurant name) -> "Food & Dining"
    - a known shopping site or store (Amazon, Flipkart, Myntra, Meesho, Nykaa) -> "Shopping"
    - a grocery/supermarket (Dmart, BigBasket, Blinkit, supermarket) -> "Groceries"
    - a transport/travel brand (Uber, Ola, IRCTC, petrol pump, Toll) -> "Transport"
    - a utility (Airtel, Jio, electricity, LPG) -> "Utilities"
    - a subscription/entertainment (Netflix, Spotify, PVR) -> "Entertainment"
    - a school/tuition provider -> "Education"
    - salary/interest/refund credited -> "Income"
    - otherwise, when "desc" is only a person's name -> "Other"
Set opening_balance / closing_balance to null when the document does not show opening and closing balances (e.g. a receipt)."""


# ---------------------------------------------------------------------------
# #2 — Pre-check
# ---------------------------------------------------------------------------

def validate_upload(name, size):
    """Basic type/size gate before anything expensive runs.

    Returns an error message string, or None when the file is acceptable.
    """
    if not name:
        return "No file selected."
    ext = os.path.splitext(str(name))[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"Unsupported file type '.{ext or 'unknown'}'. Use JSON, PDF, PNG, JPG or JPEG."
    if size and size > MAX_UPLOAD_BYTES:
        return "File is too large (max 20 MB)."
    return None


# ---------------------------------------------------------------------------
# #4 — Schema sanity + balance reconciliation helpers
# ---------------------------------------------------------------------------

def normalize_transaction_date(raw_date, now=None):
    """Resolve the transaction's stored timestamp from what the statement states.

    Rule (per the user's requirement):
      * If the statement reports an exact time, THAT time is stored verbatim —
        the day AND the time are never rewritten.
      * If the statement gives only a date (`YYYY-MM-DD`), the time part is taken
        from the moment of extraction (`now`) instead of defaulting to midnight.
        Why midnight is wrong: the anomaly engine flags every transaction whose
        hour is 0-5 as a "late-night" temporal anomaly (`0 <= hour <= 5`), so
        date-only rows all defaulting to 00:00:00 fire fraud emails on every
        statement — mass false positives. A real statement rarely carries a time
        for UPI/POS rows, so the honest "time of day" is the scan clock.
      * An explicit `00:00:00` in the input is a REPORTED time and stays as-is.

    The DAY is always preserved — that invariant (the system never moves a
    transaction's date) still holds; only the time-of-day is filled in.

    Returns None when the date is entirely missing — callers drop/flag the row
    instead of inventing a day.
    """
    raw = str(raw_date or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        now = now or datetime.now()
        return f"{raw} {now.strftime('%H:%M:%S')}"
    return raw


# ---------------------------------------------------------------------------
# #4b — Description cleaning + merchant categorization
# ---------------------------------------------------------------------------
# Indian bank statements narrate UPI payments verbatim, e.g.
#   "UPI 004478649026/YESB/SURBHI DURGESH GUPTA/Paid vi"
# That string is useless for display AND for categorisation (the AI sees a
# random-looking blob and guesses "Other" instead of reading the merchant). We
# strip the noise down to the counterparty's name, then categorise from that
# name deterministically — no AI, no LLM, works for both OCR and JSON uploads.

# Prefix markers that start many narrations ("UPI 004478649026", "NEFT X", ...).
_NARRATION_PREFIXES = ("upi", "neft", "imps", "rtgs", "pos", "atm", "nam",
                       "ach", "chq", "cheque", "bharat", "dd")

# All-caps bank codes that appear as their own segment in UPI narrations.
_BANK_CODES = frozenset({
    "yesb", "ybl", "pytm", "yun", "npci", "hdfc", "icic", "sbin", "sbp",
    "axis", "kotak", "utib", "indus", "induslnd", "idib", "idfb", "auib",
    "jsfb", "kvbl", "dcbl", "ratn", "ucob", "tmb", "fdrl", "cbi", "bob",
    "bkid", "barb", "cnrb", "punb", "ubin", "mahb", "psbl", "sbm", "fb",
    "ibkl", "citi", "hsbc", "cms", "fino", "imes", "aubk",
})

# Remark / boilerplate words. A segment whose words are ALL in this set (e.g.
# "Paid vi", "Via UPI") is dropped as narration noise.
_NOISE_WORDS = frozenset({
    "upi", "paid", "via", "vi", "trf", "transfer", "nft", "ims", "for",
    "by", "to", "on", "current", "saving", "ac", "act", "apb", "a2a",
    "p2p", "collect", "ref", "get", "sent", "received", "recv", "mobile",
    "mor", "na", "msg",
})


def clean_description(raw):
    """Strip UPI/NEFT/IMPS narration noise down to the counterparty's name.

      "UPI 004478649026/YESB/SURBHI DURGESH GUPTA/Paid vi" -> "SURBHI DURGESH GUPTA"
      "NEFT RMG0000123/HDFC/MCDONALDS"                        -> "MCDONALDS"
      "SWIGGY"                                                -> "SWIGGY" (no change)

    Pure heuristics — a narration with no recognisable noise passes through
    untouched, and a bad match degrades to a best-effort strip, never to an
    empty string for a non-empty input.
    """
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""

    def _is_noise_word(w):
        low = w.lower()
        if re.fullmatch(r"\d+", low):
            return True
        # Reference codes mix letters + digits ("RMG0000123", "UPI0044786") —
        # never a counterparty name.
        if re.search(r"[a-z]", low) and any(c.isdigit() for c in low):
            return True
        return (low in _NOISE_WORDS or low in _BANK_CODES
                or low in _NARRATION_PREFIXES)

    kept = []
    for segment in s.split("/"):
        seg = segment.strip()
        if not seg:
            continue
        # A whole segment that is just a UPI reference / handle / bank code.
        low = seg.lower()
        if re.fullmatch(r"\d+|[a-z0-9._-]+@[a-z0-9._-]+", low):
            continue
        words = [w for w in re.split(r"\s+", seg.strip()) if w]
        if all(_is_noise_word(w) for w in words):
            continue
        kept.append(seg)

    name = " ".join(kept).strip(" /-")
    # A trailing remark that snuck through as one segment ("refna", "paid vi").
    name = re.sub(r"\s+(paid\s?vi|paid\s?via|via\s+upi|ref\w*)\s*$",
                  "", name, flags=re.IGNORECASE).strip()
    if name:
        return name

    # A lone UPI handle ("RAHUL@YBL") -> the person behind it ("RAHUL").
    m = re.match(r"([a-z0-9._-]+)@[a-z0-9._-]+$", s.strip(), flags=re.IGNORECASE)
    if m and not re.fullmatch(r"\d+", m.group(1)):
        return m.group(1)
    # Fallback: drop the leading UPI/NEFT marker and any leading digits only.
    stripped = re.sub(r"^(upi|neft|imps|rtgs|pos|atm|chq|cheque|dd|bharat)"
                      r"[\s/:\.-]+", "", s, flags=re.IGNORECASE)
    stripped = re.sub(r"^\d+[\s/:\.-]+", "", stripped).strip(" /-")
    return stripped or s


# (category, keyword) pairs — longest keyword first so "big basket" beats "big".
_MERCHANT_KEYWORDS = [
    ("Food & Dining", ["zomato", "swiggy", "eatclub", "dominos", "domino's",
                       "pizza hut", "pizzahut", "kfc", "mcdonald", "subway",
                       "starbucks", "cafe coffee day", "ccd", "barbeque nation",
                       "barbecue", "haldiram", "bikanervala", "biryani by",
                       "box8", "faasos", "eatfit", "faasos", "burger king",
                       "taco bell", "dunkin", "baskin robins", "potbelly",
                       "annapurna", "saravana bhavan", "udupi", "tiffin",
                       "restaurant", "dhaba", "cafe", "coffee", "biryani",
                       "bhojanalaya", "sweets", "mithai", "bakery", "canteen"]),
    ("Shopping", ["amazon", "amzn", "flipkart", "myntra", "ajio", "meesho",
                  "snapdeal", "nykaa", "tata cliq", "tatacliq", "lenskart",
                  "croma", "vijay sales", "reliance digital", "shoppers stop",
                  "lifestyle", "pantaloons", "westside", "levis", "h&m",
                  "zara", "max fashion", "relaxo", "woodland", "koovs",
                  "cashify", "clothing", "fashion"]),
    # Groceries must be checked BEFORE the Shopping fallbacks above are too
    # broad — here the grocery merchants are specific, so ordering is safe.
    ("Groceries", ["dmart", "big basket", "bigbasket", "bbnow", "reliance smart",
                   "reliance fresh", "spencers", "spencer's", "more retail",
                   "easyday", "kirana", "grocery", "supermarket", "blinkit",
                   "zepto", "instamart", "grofers", "farmrishi", "nature's basket",
                   "apna bazaar", "swadeshi", "subhiksha", "milk", "sabzi",
                   "vegetable", "fruits", "general store", "provision"]),
    ("Transport", ["uber", "ola", "rapido", "yulu", "blusmart", "irctc",
                   "redbus", "red bus", "makemytrip", "goibibo", "cleartrip",
                   "ixigo", "bmtc", "best", "nmmc", "metro", "auto rickshaw",
                   "taxi", "petrol", "diesel", "fuel", "indian oil", "hpcl",
                   "bpcl", "bharat petroleum", "nayara", "shell", "fastag",
                   "toll", "parking", "train", "flight", "ticket"]),
    ("Utilities", ["airtel", "jio", "vi recharge", "vodafone", "idea",
                   "bsnl", "recharge", "prepaid", "postpaid", "broadband",
                   "act fiber", "hathway", "internet", "electricity", "power",
                   "bescom", "mahavitaran", "mahanagar gas", "indane",
                   "hp gas", "bharat gas", "lpg", "gas bill", "water bill",
                   "igl", "mgl", "tata power"]),
    ("Entertainment", ["netflix", "spotify", "amazon prime", "prime video",
                       "hotstar", "disney", "sony liv", "sonyliv", "zee5",
                       "jiocinema", "youtube", "audible", "gaana",
                       "bookmyshow", "book my show", "pvr", "inox", "steam",
                       "playstation", "xbox", "subscription", "cinema"]),
    ("Income", ["salary", "refund", "interest", "dividend", "credit",
                "payout", "apy", "kisan", "rebate"]),
    ("Education", ["byju's", "byjus", "unacademy", "udemy", "coursera",
                   "vedantu", "khan academy", "toppr", "vedic", "school",
                   "college", "tuition", "book store", "stationery"]),
]

_CATEGORY_BY_KEYWORD = {}
for _cat, _kws in _MERCHANT_KEYWORDS:
    for _kw in _kws:
        _CATEGORY_BY_KEYWORD.setdefault(_kw.lower(), _cat)


def categorize_description(desc):
    """Return the canonical category for a merchant name, or None.

    Matching tolerates the messy names statements actually carry: punctuation
    ("D-Mart"), plurals ("MCDONALDS"), dense concatenations ("RELIANCE SMART").
    Both a whitespace-boundary match (for multi-word keywords like "big basket")
    and an alphanumeric-normalised substring match (D-Mart -> dmart) are tried.
    """
    low = re.sub(r"\s+", " ", str(desc or "").strip().lower()).strip(" .,-")
    if not low:
        return None
    low2 = re.sub(r"[^a-z0-9]+", "", low)
    for kw, cat in sorted(_CATEGORY_BY_KEYWORD.items(),
                          key=lambda kv: len(kv[0]), reverse=True):
        if low == kw or low.startswith(kw + " ") or low.endswith(" " + kw) \
                or f" {kw} " in f" {low} ":
            return cat
        kw2 = re.sub(r"[^a-z0-9]+", "", kw)
        # Substring guard — at least 3 chars so "vi"/"jio" style fragments in
        # unrelated words never hijack a category.
        if kw2 and len(kw2) >= 3 and kw2 in low2:
            return cat
    return None


# ── Post-extraction direction safeguard ─────────────────────────────────
# Indian bank narrations embed explicit direction cues in the RAW text.
# Gemini sometimes gets the column wrong; these keyword sets catch the most
# common misclassifications by scanning the original (un-cleaned) description.

# Words that prove money LEFT the account → must be Expense
_EXPENSE_DIRECTION_WORDS = frozenset({
    "debited", "debit", "dr",
    "atm", "pos", "swipe", "tap",
    "paid", "payment", "sent", "transfer", "transferred",
    "emi", "sip", "auto-debit", "autodebit", "autopay",
    "withdrawal", "cheque", "chq",
    "nach", "emandate",
})

# Words that prove money ENTERED the account → must be Income
_INCOME_DIRECTION_WORDS = frozenset({
    "credited", "credit", "cr",
    "salary", "sal",
    "interest", "refund", "cashback",
    "dividend", "maturity",
    "received",
})

# False-positive guards: these PHRASES look like income ("credit") but are
# actually money LEAVING the account. When present, the bare "credit" word is
# discarded (a "credit card payment" is an Expense).
_EXPENSE_PHRASES = ("credit card", "creditcard", "fixed deposit", "card payment")


def _correct_type_from_narration(raw_desc, current_type):
    """Fix misclassified type by scanning the raw narration for direction cues.

    This runs on the ORIGINAL description text (before clean_description strips
    UPI noise). A UPI narration like "UPI 123/YESB/RAHUL/Paid vi" carries the
    word "Paid" which gets removed during cleaning — but it's the strongest
    signal that money LEFT the account.

    Some words are ambiguous and MUST NOT fire alone:
      * "credit" inside "credit card payment" is an EXPENSE, not income.
      * "deposited" is NOT a reliable cue at all (a "fixed deposit" is money
        out, a cash deposit is money in) so it is omitted entirely.
      * "dr" matches a doctor's-name prefix too, which is also an expense — fine.

    Returns the corrected type ("Expense" or "Income").
    """
    low = str(raw_desc or "").lower()
    flat = re.sub(r"[^a-z\s]", " ", low)
    words = set(flat.split())

    if any(p in low for p in _EXPENSE_PHRASES):
        # "credit card payment" doesn't mean income arrived.
        words.discard("credit")
        words.discard("credited")

    expense_hits = words & _EXPENSE_DIRECTION_WORDS
    income_hits = words & _INCOME_DIRECTION_WORDS

    if expense_hits and not income_hits:
        return "Expense"
    if income_hits and not expense_hits:
        return "Income"
    # Both or neither → trust the caller's type_val
    return current_type


def validate_transactions(raw_list, now=None):
    """Drop malformed rows, coerce types, and warn about what was skipped.

    Descriptions are passed through `clean_description()` (UPI narration noise
    stripped to the counterparty's name) and re-categorised deterministically:
      * a known merchant (restaurant/shop/etc.) maps to its category,
      * a UPI narration that reduced to a person's name -> "Other",
      * otherwise the supplied/AI category is kept.

    `now` is the extraction wall-clock (injectable for deterministic tests) —
    date-only rows borrow its time-of-day so they don't all land on midnight
    (which the anomaly engine flags as "late-night"). Every date-only row in one
    scan shares the same extraction second.

    Returns (clean_list, warnings). A clean row is:
      {"desc", "amount" (float > 0), "category", "type" (Expense/Income), "date"}
    """
    clean, warnings = [], []
    if not isinstance(raw_list, list):
        return clean, ["Extraction did not return a list of transactions."]
    scan_now = now or datetime.now()

    for i, txn in enumerate(raw_list, start=1):
        if not isinstance(txn, dict):
            warnings.append(f"Row {i} skipped: not an object.")
            continue
        desc = str(txn.get("desc") or txn.get("description") or "").strip()
        if not desc:
            warnings.append(f"Row {i} skipped: no description.")
            continue
        try:
            amount = float(txn.get("amount", 0.0))
        except (TypeError, ValueError):
            warnings.append(f"Row {i} skipped: amount '{txn.get('amount')}' is not a number.")
            continue
        if amount <= 0:
            warnings.append(f"Row {i} skipped: amount must be positive (got {amount}).")
            continue
        type_val = str(txn.get("type", "Expense")).strip()
        if type_val not in ("Expense", "Income"):
            type_val = "Expense"

        # Post-extraction safeguard: the narration text often contradicts the
        # type Gemini inferred from the columns (a "Paid vi" tail, an ATM marker,
        # a "Salary credited" prefix). Correct overridably-wrong directions here.
        type_val = _correct_type_from_narration(desc, type_val)

        # Normalise the date first — a missing/empty date means we cannot
        # reliably place this row; skip it instead of inventing "today".
        date_norm = normalize_transaction_date(txn.get("date"), scan_now)
        if date_norm is None:
            warnings.append(
                f"Row {i} skipped: transaction has no date."
            )
            continue

        # ── Category rule (order matters) ──────────────────────────────
        # Rule 1: Money credited → always Income (overrides everything
        # else, including AI guesses).
        clean_desc = desc   # default; overwritten below for Expense rows
        if type_val == "Income":
            category = "Income"
        else:
            # Rule 2: Deterministic merchant override for Expense rows.
            cleaned = clean_description(desc)
            clean_desc = cleaned if cleaned else desc
            merchant_cat = categorize_description(clean_desc)
            if merchant_cat:
                category = merchant_cat
            elif cleaned != desc.strip():
                # UPI cleaned to a person name we don't recognise → Other
                category = "Other"
            else:
                category = str(txn.get("category", "Other")).strip() or "Other"

        clean.append({
            "desc": clean_desc,
            "amount": round(amount, 2),
            "category": category,
            "type": type_val,
            "date": date_norm,
        })
    return clean, warnings


def reconcile(txns, opening_balance, closing_balance):
    """Arithmetic check: closing ≈ opening + Σ(Income − Expense).

    Advisory only — a statement without balances (a receipt, a slim JSON)
    returns status "skipped" and never strands the data upstream.
    """
    if opening_balance is None or closing_balance is None:
        return {"status": "skipped", "diff": None,
                "message": "No opening/closing balance to check — skipped."}
    try:
        opening = float(opening_balance)
        closing = float(closing_balance)
    except (TypeError, ValueError):
        return {"status": "skipped", "diff": None,
                "message": "Balances are not numeric — skipped."}
    net = sum(t["amount"] if t["type"] == "Income" else -t["amount"] for t in txns)
    expected = opening + net
    diff = abs(expected - closing)
    if diff <= 1.0:  # ₹1 tolerance for rounding in extracted figures
        return {"status": "ok", "diff": round(diff, 2),
                "message": f"Opening {opening:,.2f} + net {net:,.2f} = {expected:,.2f} matches closing {closing:,.2f}."}
    return {"status": "mismatch", "diff": round(diff, 2),
            "message": (f"Reconciliation is off by ₹{diff:,.2f}: expected closing {expected:,.2f}, "
                        f"extracted closing is {closing:,.2f}. The extraction may be wrong.")}


# ---------------------------------------------------------------------------
# #5 — Dedup + persistence
# ---------------------------------------------------------------------------

def _norm_narration(narration):
    """Lower-cased, collapsed counterparty name used in the dedup key.

    Stored descriptions are Fernet-encrypted (non-deterministic ciphertext), so
    they can never be compared at rest — but the CLEANED name is deterministic
    (same statement -> same cleaned name), which is all the key needs.
    """
    return clean_description(str(narration or "")).strip().lower()


def fingerprint(amount, date_str, account_id=None, narration=None):
    """Identity key for a transaction row.

    (amount, date[:10], account_id, cleaned_narration). Date-granularity ([:10])
    on purpose: the OCR path stamps date-only rows with the CURRENT scan time, so
    two scans of the same statement differ by seconds — a minute-granularity key
    would never match re-scans. The account discriminates accounts so an
    identical amount+date in two different accounts is not collapsed.

    The narration (cleaned, not the encrypted ciphertext) is PART of the key:
    two *different* people/merchants who paid the same amount on the same day
    must not be collapsed into one row, while a re-scan of the same statement
    still dedupes because its cleaned names are identical.
    """
    return (round(float(amount), 2), str(date_str)[:10], str(account_id or ""),
            _norm_narration(narration))


def persist_with_dedup(supabase, user_id, user_email, user_name, account_id,
                       account_name, txns, decrypt_fn=None):
    """Insert validated transactions, skipping any that already exist.

    Dedup is application-level (the tables already contain duplicates, so a DB
    UNIQUE index cannot be added) and runs on the parsed plaintext BEFORE
    encryption — description ciphertext is non-deterministic (Fernet), so it
    can never be compared at rest. Stored rows are decrypted and cleaned so
    their counterparty name joins the key.

    Rows whose stored narration can't be read (empty, or legacy rows masked to
    "********" after a key change) fall back to the legacy (amount, date,
    account) key so re-scans still dedupe. `decrypt_fn` is injectable for tests.

    Returns {"inserted": int, "duplicates": int, "error": str | None}.
    Never raises.
    """
    try:
        decrypt = decrypt_fn or decrypt_data
        existing_res = (supabase.table("transactions")
                        .select("amount, transaction_time, account_id, description")
                        .eq("user_id", user_id).execute())
        existing_named, existing_legacy = set(), set()
        for t in (existing_res.data or []):
            try:
                amt = float(t.get("amount"))
                ts = str(t.get("transaction_time") or "")
                acc = t.get("account_id")
                enc_desc = t.get("description") or ""
                plain = decrypt(enc_desc) if enc_desc else ""
                narr = plain if plain and plain != "********" else ""
                if narr:
                    existing_named.add(fingerprint(amt, ts, acc, narr))
                else:
                    existing_legacy.add(fingerprint(amt, ts, acc))
            except (TypeError, ValueError):
                pass

        new_rows, skipped = [], 0
        plain = []  # plaintext descriptions, aligned with new_rows — the
                    # anomaly engine needs readable text, but `desc` is NOT a
                    # DB column, so it must never be sent to Supabase.
        for t in txns:
            desc_plain = str(t.get("desc") or "")
            named_key = fingerprint(t["amount"], t["date"], account_id, desc_plain)
            legacy_key = fingerprint(t["amount"], t["date"], account_id)
            if named_key in existing_named or legacy_key in existing_legacy:
                skipped += 1
                continue
            # dupes within one statement too — subsequent identical rows hit our set.
            existing_named.add(named_key)
            new_rows.append({
                "user_id": user_id,
                "account_id": account_id,
                "transaction_time": t["date"],
                "description": encrypt_data(t["desc"]),
                "amount": t["amount"],
                "category": t["category"],
                "type": t["type"],
            })
            plain.append(t["desc"])

        inserted = 0
        if new_rows:
            ins_res = supabase.table("transactions").insert(new_rows).execute()
            new_ids = [r["id"] for r in (ins_res.data or []) if r.get("id")]
            inserted = len(new_ids)
            # Fire the anomaly engine for scanned expenses, excluding the rows
            # just created so a big new spend isn't masked by its own amount.
            for i, t in enumerate(new_rows):
                if t["type"] == "Expense":
                    check_and_alert_anomaly(
                        supabase=supabase,
                        user_id=user_id,
                        user_email=user_email,
                        user_name=user_name,
                        amount=t["amount"],
                        category=t["category"],
                        description=plain[i],
                        transaction_time_iso=t["transaction_time"],
                        account_name=account_name,
                        exclude_ids=new_ids,
                    )
        return {"inserted": inserted, "duplicates": skipped, "error": None}
    except Exception as e:
        return {"inserted": 0, "duplicates": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# #3 — AI extraction (OCR)
# ---------------------------------------------------------------------------

def _nullable_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def extract_with_gemini(client, model, file_bytes, mime_type=None, filename="scan.jpg"):
    """Send a PDF/image to Gemini and parse the transaction JSON back.

    Accepts either the documented object shape ({opening_balance,
    closing_balance, transactions: [...]}) or the legacy bare-array shape.
    Never throws — on any failure returns {"transactions": [], …,
    "error": str(e)}.
    """
    result = {"transactions": [], "opening_balance": None,
              "closing_balance": None, "error": None}
    temp_path, gemini_file = None, None
    try:
        ext = os.path.splitext(str(filename))[1].lower()
        mime = mime_type or _MIME_BY_EXT.get(ext, "application/octet-stream")
        suffix = ext or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
            tf.write(file_bytes)
            temp_path = tf.name

        gemini_file = client.upload_file(path=temp_path, mime_type=mime)
        response = model.generate_content([_EXTRACTION_PROMPT, gemini_file])
        text = getattr(response, "text", "") or ""

        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        data = None
        if obj_match:
            try:
                data = json.loads(obj_match.group(0))
            except Exception:
                data = None

        # Object shape (documented): only accepted when it carries transactions.
        if isinstance(data, dict) and "transactions" in data:
            txs = data.get("transactions")
            result["transactions"] = txs if isinstance(txs, list) else []
            result["opening_balance"] = _nullable_float(data.get("opening_balance"))
            result["closing_balance"] = _nullable_float(data.get("closing_balance"))
            return result

        # Legacy bare-array shape. Note a single-element array parses as a dict
        # from the {.*} match above and falls through to here — that is fine.
        arr_match = re.search(r"\[.*\]", text, re.DOTALL)
        if arr_match:
            try:
                arr = json.loads(arr_match.group(0))
            except Exception:
                arr = None
            if isinstance(arr, list):
                result["transactions"] = arr
                return result

        result["error"] = "AI did not return a valid JSON response."
        return result
    except Exception as e:
        result["error"] = str(e)
        return result
    finally:
        if gemini_file is not None:
            try:
                client.delete_file(gemini_file.name)
            except Exception:
                pass
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass