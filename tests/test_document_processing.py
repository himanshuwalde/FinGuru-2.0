"""Tests for services/document_processing.py — the shared upload pipeline."""
from datetime import datetime
from unittest.mock import MagicMock, patch

from services import document_processing as dp

# ---------------------------------------------------------------------------
# validate_upload — type/size pre-check
# ---------------------------------------------------------------------------

class TestValidateUpload:
    def test_no_file(self):
        assert dp.validate_upload(None, 0) == "No file selected."
        assert dp.validate_upload("", 0) == "No file selected."

    def test_unsupported_extension(self):
        assert "Unsupported" in dp.validate_upload("data.csv", 1000)

    def test_oversized(self):
        assert "too large" in dp.validate_upload("stmt.pdf", dp.MAX_UPLOAD_BYTES + 1).lower()

    def test_accepts_json(self):
        assert dp.validate_upload("data.json", 100) is None

    def test_accepts_pdf(self):
        assert dp.validate_upload("stmt.pdf", 100) is None

    def test_accepts_jpg(self):
        assert dp.validate_upload("scan.jpg", 100) is None

    def test_accepts_jpeg(self):
        assert dp.validate_upload("scan.jpeg", 100) is None

    def test_accepts_png(self):
        assert dp.validate_upload("scan.png", 100) is None


# ---------------------------------------------------------------------------
# normalize_transaction_date — exact-time / extraction-time rule
# ---------------------------------------------------------------------------

class TestNormalizeTransactionDate:
    FIXED = datetime(2026, 9, 16, 14, 23, 45)

    def test_date_only_uses_extraction_time_not_midnight(self):
        """Bare 'YYYY-MM-DD' gets the EXTRACTION clock time — not 00:00:00.

        Midnight (hour 0) trips the anomaly engine's late-night check
        (0 <= hour <= 5); a real scan clock keeps daytime rows unflagged.
        """
        assert dp.normalize_transaction_date("2026-09-16", now=self.FIXED) == "2026-09-16 14:23:45"

    def test_date_only_defaults_to_real_now_when_not_injected(self):
        """Without `now`, the real clock is used (extraction wall-clock)."""
        result = dp.normalize_transaction_date("2026-09-16")
        assert result.startswith("2026-09-16 ")

    def test_exact_statement_time_preserved(self):
        """A statement-reported time is stored VERBATIM — never rewritten."""
        assert dp.normalize_transaction_date("2026-09-16 09:15:30") == "2026-09-16 09:15:30"

    def test_reported_midnight_stays_midnight(self):
        """An explicit 00:00:00 in the input is a REPORTED time — keep it."""
        assert dp.normalize_transaction_date("2026-09-16 00:00:00") == "2026-09-16 00:00:00"

    def test_empty_returns_none(self):
        """Missing date returns None — callers skip the row instead of inventing a day."""
        assert dp.normalize_transaction_date("") is None
        assert dp.normalize_transaction_date(None) is None

    def test_day_never_changes(self):
        """The DATE part is invariant — only the time-of-day is filled in."""
        assert dp.normalize_transaction_date("2026-09-01", now=self.FIXED).startswith("2026-09-01 ")


# ---------------------------------------------------------------------------
# validate_transactions — schema sanity
# ---------------------------------------------------------------------------

class TestValidateTransactions:
    def test_empty_list(self):
        assert dp.validate_transactions([]) == ([], [])

    def test_non_list_input(self):
        clean, warns = dp.validate_transactions("bad")
        assert clean == []
        assert len(warns) == 1

    def test_drops_missing_desc(self):
        clean, warns = dp.validate_transactions([{"amount": 100, "type": "Expense", "date": "2026-01-01"}])
        assert clean == []
        assert any("description" in w.lower() for w in warns)

    def test_drops_non_numeric_amount(self):
        clean, warns = dp.validate_transactions([{"desc": "X", "amount": "abc", "type": "Expense", "date": "2026-01-01"}])
        assert clean == []

    def test_drops_negative_amount(self):
        clean, warns = dp.validate_transactions([{"desc": "X", "amount": -5, "type": "Expense", "date": "2026-01-01"}])
        assert clean == []

    def test_coerces_invalid_type_to_expense(self):
        clean, _ = dp.validate_transactions([{"desc": "X", "amount": 10, "type": "Weird", "date": "2026-01-01"}])
        assert clean[0]["type"] == "Expense"

    def test_valid_row_passes(self):
        clean, warns = dp.validate_transactions([{
            "desc": "Coffee", "amount": 250.5, "category": "Food & Dining",
            "type": "Expense", "date": "2026-09-16"
        }])
        assert len(clean) == 1
        assert clean[0]["amount"] == 250.5


# ---------------------------------------------------------------------------
# reconcile — balance check
# ---------------------------------------------------------------------------

class TestReconcile:
    def test_skipped_when_no_balances(self):
        r = dp.reconcile([], None, None)
        assert r["status"] == "skipped"

    def test_ok_when_balances_match(self):
        txns = [{"type": "Income", "amount": 500}, {"type": "Expense", "amount": 200}]
        # opening 1000 + net(500-200) = 1300
        r = dp.reconcile(txns, 1000, 1300)
        assert r["status"] == "ok"

    def test_mismatch_when_off(self):
        txns = [{"type": "Expense", "amount": 100}]
        r = dp.reconcile(txns, 1000, 800)  # expected 900, got 800
        assert r["status"] == "mismatch"
        assert r["diff"] == 100.0


# ---------------------------------------------------------------------------
# fingerprint — identity key
# ---------------------------------------------------------------------------

class TestFingerprint:
    def test_same_amount_date(self):
        assert dp.fingerprint(100.0, "2026-09-16 10:00:00") == (100.0, "2026-09-16", "", "")

    def test_different_amount_not_equal(self):
        assert dp.fingerprint(100.0, "2026-09-16") != dp.fingerprint(200.0, "2026-09-16")

    def test_same_date_different_time_equal(self):
        """Date-granularity [:10] — two times on same date match."""
        assert dp.fingerprint(100.0, "2026-09-16 08:00:00") == dp.fingerprint(100.0, "2026-09-16 22:00:00")

    def test_different_account_not_equal(self):
        """Tightened key — same amount+date in different accounts is distinct."""
        assert dp.fingerprint(100.0, "2026-09-16", "a1") != dp.fingerprint(100.0, "2026-09-16", "a2")

    def test_same_account_same_amount_date_equal(self):
        assert dp.fingerprint(100.0, "2026-09-16", "a1") == dp.fingerprint(100.0, "2026-09-16", "a1")

    def test_different_narration_not_equal(self):
        """THE DEDUP FIX — same amount+date+account, different counterparty."""
        assert (dp.fingerprint(250.0, "2026-09-16", "a1", "SURBHI GUPTA")
                != dp.fingerprint(250.0, "2026-09-16", "a1", "RAHUL SHARMA"))

    def test_same_narration_equal(self):
        """Same person A->B and B->A both clean to the merchant name."""
        assert (dp.fingerprint(250.0, "2026-09-16", "a1", "ZOMATO ONLINE")
                == dp.fingerprint(250.0, "2026-09-16", "a1", "Zomato online"))

    def test_narration_cleaned_in_key(self):
        """Noisy UPI narration normalises to the same key as its clean name."""
        key_noisy = dp.fingerprint(500.0, "2026-09-16", "a1",
                                   "UPI 12345/YESB/SURBHI DURGESH GUPTA/Paid vi")
        key_clean = dp.fingerprint(500.0, "2026-09-16", "a1", "SURBHI DURGESH GUPTA")
        assert key_noisy == key_clean


# ---------------------------------------------------------------------------
# clean_description — UPI/NEFT narration noise stripping
# ---------------------------------------------------------------------------

class TestCleanDescription:
    def test_upi_long_form(self):
        assert dp.clean_description(
            "UPI 004478649026/YESB/SURBHI DURGESH GUPTA/Paid vi"
        ) == "SURBHI DURGESH GUPTA"

    def test_upi_slash_format(self):
        assert dp.clean_description(
            "UPI/149209821397/INDUSLND/MCDONALDS/"
        ) == "MCDONALDS"

    def test_neft(self):
        assert dp.clean_description(
            "NEFT RMG0000123/HDFC/AMAZON"
        ) == "AMAZON"

    def test_passes_through_plain_merchant(self):
        assert dp.clean_description("SWIGGY") == "SWIGGY"

    def test_lone_upi_handle_yields_person(self):
        assert dp.clean_description("RAHUL@YBL") == "RAHUL"

    def test_empty_input(self):
        assert dp.clean_description("") == ""
        assert dp.clean_description(None) == ""


# ---------------------------------------------------------------------------
# categorize_description — deterministic merchant -> category
# ---------------------------------------------------------------------------

class TestCategorizeDescription:
    def test_food(self):
        assert dp.categorize_description("ZOMATO") == "Food & Dining"
        assert dp.categorize_description("KFC") == "Food & Dining"

    def test_shopping(self):
        assert dp.categorize_description("AMAZON") == "Shopping"
        assert dp.categorize_description("Flipkart") == "Shopping"

    def test_groceries(self):
        assert dp.categorize_description("D-Mart") == "Groceries"  # dmart token
        assert dp.categorize_description("BIGBASKET") == "Groceries"

    def test_person_name_unknown(self):
        """A person's name matches no merchant -> None (caller maps to Other)."""
        assert dp.categorize_description("SURBHI DURGESH GUPTA") is None

    def test_empty(self):
        assert dp.categorize_description("") is None
        assert dp.categorize_description(None) is None


# ---------------------------------------------------------------------------
# _correct_type_from_narration — debited/credited direction safeguard
# ---------------------------------------------------------------------------

class TestCorrectTypeFromNarration:
    def test_upi_paid_tail_means_expense(self):
        """'Paid vi' shows money left the account — even if Gemini said Income."""
        assert dp._correct_type_from_narration(
            "UPI 004478649026/YESB/SURBHI DURGESH GUPTA/Paid vi", "Income"
        ) == "Expense"

    def test_atm_withdrawal_is_expense(self):
        assert dp._correct_type_from_narration("ATM WITHDRAWAL SBI 1234", "Income") == "Expense"

    def test_salary_credited_means_income(self):
        """'Salary credited' shows money arrived — even if Gemini said Expense."""
        assert dp._correct_type_from_narration("NEFT/CREDIT/SALARY/XYZ CORP", "Expense") == "Income"

    def test_interest_credited_is_income(self):
        assert dp._correct_type_from_narration("FD INTEREST CREDITED", "Expense") == "Income"

    def test_credit_card_payment_is_expense_not_income(self):
        """'credit' inside 'credit card payment' must NOT read as income."""
        assert dp._correct_type_from_narration("CREDIT CARD PAYMENT", "Expense") == "Expense"

    def test_plain_merchant_has_no_cue_keeps_type(self):
        """No direction words -> trust the caller's type."""
        assert dp._correct_type_from_narration("AMAZON", "Income") == "Income"
        assert dp._correct_type_from_narration("ZOMATO", "Expense") == "Expense"
        assert dp._correct_type_from_narration("SURBHI DURGESH GUPTA", "Expense") == "Expense"

    def test_ambivalent_narration_keeps_type(self):
        """Both cues present -> too ambiguous, trust caller."""
        assert dp._correct_type_from_narration("NEFT TRANSFER RECEIVED FROM ROHAN", "Expense") == "Expense"


# ---------------------------------------------------------------------------
# validate_transactions — cleaning + categorisation integration
# ---------------------------------------------------------------------------

class TestValidateCategorisation:
    def test_upi_person_becomes_other_even_if_ai_shopped(self):
        clean, _ = dp.validate_transactions([{
            "desc": "UPI 004478649026/YESB/SURBHI DURGESH GUPTA/Paid vi",
            "amount": 300, "category": "Shopping", "type": "Expense",
            "date": "2026-09-16",
        }])
        assert clean[0]["desc"] == "SURBHI DURGESH GUPTA"
        assert clean[0]["category"] == "Other"

    def test_merchant_name_overrides_noisy_category(self):
        clean, _ = dp.validate_transactions([{
            "desc": "UPI 12345/YESB/ZOMATO/Paid vi",
            "amount": 450, "category": "Other", "type": "Expense",
            "date": "2026-09-16",
        }])
        assert clean[0]["category"] == "Food & Dining"

    def test_keeps_ai_category_for_plain_desc(self):
        clean, _ = dp.validate_transactions([{
            "desc": "Electricity bill", "amount": 1000, "category": "Utilities",
            "type": "Expense", "date": "2026-09-16",
        }])
        assert clean[0]["category"] == "Utilities"

    def test_income_type_forces_income_category(self):
        """Rule 1: credited = Income, regardless of AI category guess."""
        clean, _ = dp.validate_transactions([{
            "desc": "Salary credited", "amount": 85000,
            "category": "Groceries",  # wrong AI guess — ignored
            "type": "Income", "date": "2026-09-16",
        }])
        assert len(clean) == 1
        assert clean[0]["category"] == "Income"

    def test_upi_debit_misread_as_income_is_corrected(self):
        """THE BUG: a debited 'Paid vi' UPI must not surface as credited income.

        If Gemini typed a UPI payment as Income, the narration's 'Paid' tail
        forces type back to Expense — and the merchant maps the category, so the
        row shows as a red '-' debit, not a green '+' credit.
        """
        clean, _ = dp.validate_transactions([{
            "desc": "UPI 12345/YESB/ZOMATO/Paid vi",
            "amount": 450, "category": "Income",  # wrong AI guess
            "type": "Income",                      # wrong AI direction
            "date": "2026-09-16",
        }])
        assert clean[0]["type"] == "Expense"
        assert clean[0]["category"] == "Food & Dining"

    def test_debit_misread_as_income_stays_debit(self):
        """ATM/withdrawal typed as Income is corrected to Expense."""
        clean, _ = dp.validate_transactions([{
            "desc": "ATM WITHDRAWAL SBI 1234",
            "amount": 2000, "category": "Income",
            "type": "Income", "date": "2026-09-16",
        }])
        assert clean[0]["type"] == "Expense"

    def test_missing_date_skipped_with_warning(self):
        """No date → row dropped (the system must not invent today's date)."""
        clean, warns = dp.validate_transactions([{
            "desc": "Coffee", "amount": 100,
            "category": "Food & Dining", "type": "Expense", "date": "",
        }])
        assert clean == []
        assert any("no date" in w.lower() for w in warns)

    def test_date_only_gets_extraction_time(self):
        """Date-only rows carry the extraction clock (not midnight) so they
        don't hit the anomaly engine's 0 <= hour <= 5 late-night gate."""
        fixed = datetime(2026, 9, 16, 14, 23, 45)
        clean, _ = dp.validate_transactions([{
            "desc": "Rent", "amount": 15000,
            "category": "Other", "type": "Expense", "date": "2026-09-01",
        }], now=fixed)
        assert clean[0]["date"] == "2026-09-01 14:23:45"

    def test_all_date_only_rows_share_same_extraction_second(self):
        """Every date-only row in one scan gets the same extraction timestamp."""
        fixed = datetime(2026, 9, 16, 10, 5, 0)
        raw = [
            {"desc": "A", "amount": 100, "category": "Other", "type": "Expense", "date": "2026-09-01"},
            {"desc": "B", "amount": 200, "category": "Other", "type": "Expense", "date": "2026-09-02"},
        ]
        clean, _ = dp.validate_transactions(raw, now=fixed)
        assert clean[0]["date"] == "2026-09-01 10:05:00"
        assert clean[1]["date"] == "2026-09-02 10:05:00"


# ---------------------------------------------------------------------------
# extract_with_gemini — AI extraction stubbed
# ---------------------------------------------------------------------------

class _FakeModel:
    """Returns pre-canned JSON text from generate_content."""
    def __init__(self, text):
        self._text = text
    def generate_content(self, _args):
        resp = MagicMock()
        resp.text = self._text
        return resp


class _FakeClient:
    def __init__(self, model):
        self._model = model
    def upload_file(self, **kw):
        f = MagicMock()
        f.name = "fake"
        return f
    def delete_file(self, name):
        pass
    def GenerativeModel(self, _name):
        return self._model


class TestExtractWithGemini:
    OBJ = '{"opening_balance":1000,"closing_balance":800,"transactions":[{"desc":"X","amount":200,"category":"Food","type":"Expense","date":"2026-09-16"}]}'

    def _client(self):
        return _FakeClient(None)

    def test_object_shape(self):
        model = _FakeModel(self.OBJ)
        r = dp.extract_with_gemini(self._client(), model, b"fake", filename="stmt.pdf")
        assert r["error"] is None
        assert len(r["transactions"]) == 1
        assert r["opening_balance"] == 1000.0
        assert r["closing_balance"] == 800.0

    def test_array_fallback(self):
        arr = '[{"desc":"A","amount":50,"category":"Other","type":"Expense","date":"2026-09-16"}]'
        model = _FakeModel(arr)
        r = dp.extract_with_gemini(self._client(), model, b"fake", filename="scan.jpg")
        assert r["error"] is None
        assert len(r["transactions"]) == 1
        assert r["opening_balance"] is None

    def test_invalid_json_returns_error(self):
        model = _FakeModel("not json at all")
        r = dp.extract_with_gemini(self._client(), model, b"fake")
        assert r["error"] is not None
        assert r["transactions"] == []


# ---------------------------------------------------------------------------
# persist_with_dedup — dedup + insert + anomaly side-effects
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rows):
        self.data = rows

class _FakeTbl:
    def __init__(self, existing, insert_log):
        self._existing = existing
        self._insert_log = insert_log
    def select(self, *a):
        return self
    def eq(self, col, val):
        return self
    def execute(self):
        return _FakeResult(self._existing)
    def insert(self, rows):
        self._insert_log[:] = rows
        ins = [{"id": f"new-{i}"} for i in range(len(rows))]
        return _FakeTbl2(ins)

class _FakeTbl2:
    def __init__(self, data):
        self.data = data
    def execute(self):
        return _FakeResult(self.data)

class _FakeSupabase:
    def __init__(self, existing=None):
        self._existing = existing or []
        self.inserted_rows = []
    def table(self, name):
        return _FakeTbl(self._existing, self.inserted_rows)

TXN = {"desc": "Coffee", "amount": 250.0, "category": "Food & Dining", "type": "Expense", "date": "2026-09-16 09:00:00"}


@patch("services.document_processing.check_and_alert_anomaly")
@patch("services.document_processing.encrypt_data", side_effect=lambda x: f"enc({x})")
def test_persist_skips_duplicates(_enc, _anomaly):
    """Transaction whose fingerprint already exists in DB is skipped (same account)."""
    existing = [{"amount": 250.0, "transaction_time": "2026-09-16 08:00:00", "account_id": "a1"}]
    fake = _FakeSupabase(existing)
    res = dp.persist_with_dedup(fake, "u1", "e@e.com", "Test", "a1", "Acc", [TXN])
    assert res["inserted"] == 0
    assert res["duplicates"] == 1
    _anomaly.assert_not_called()


@patch("services.document_processing.check_and_alert_anomaly")
@patch("services.document_processing.encrypt_data", side_effect=lambda x: f"enc({x})")
def test_persist_same_amount_date_other_account_not_dup(_enc, _anomaly):
    """Same amount+date but a DIFFERENT account must NOT be a duplicate."""
    existing = [{"amount": 250.0, "transaction_time": "2026-09-16 08:00:00", "account_id": "a1"}]
    fake = _FakeSupabase(existing)
    res = dp.persist_with_dedup(fake, "u1", "e@e.com", "Test", "a2", "Acc2", [TXN])
    assert res["inserted"] == 1
    assert res["duplicates"] == 0
    _anomaly.assert_called_once()


@patch("services.document_processing.check_and_alert_anomaly")
@patch("services.document_processing.encrypt_data", side_effect=lambda x: f"enc({x})")
def test_persist_inserts_new(_enc, _anomaly):
    """Fingerprint not in DB → row inserted and anomaly fired."""
    fake = _FakeSupabase([])  # no existing
    res = dp.persist_with_dedup(fake, "u1", "e@e.com", "Test", "a1", "Acc", [TXN])
    assert res["inserted"] == 1
    assert res["duplicates"] == 0
    _anomaly.assert_called_once()
    # The insert payload must be EXACTLY the DB columns — a `desc` key here
    # would get sent to Supabase, which has no such column (PGRST204).
    assert fake.inserted_rows
    assert "desc" not in fake.inserted_rows[0]
    assert fake.inserted_rows[0]["description"] == "enc(Coffee)"


@patch("services.document_processing.check_and_alert_anomaly")
@patch("services.document_processing.encrypt_data", side_effect=lambda x: f"enc({x})")
def test_persist_exclude_ids_passed_to_anomaly(_enc, _anomaly):
    """exclude_ids from persist are forwarded to check_and_alert_anomaly."""
    fake = _FakeSupabase([])
    dp.persist_with_dedup(fake, "u1", "e@e.com", "Test", "a1", "Acc", [TXN])
    _, kwargs = _anomaly.call_args
    assert "exclude_ids" in kwargs
    assert len(kwargs["exclude_ids"]) == 1


# Two different people spending the same amount on the same day must NOT be deduped.
_decrypt_stub = lambda c: c[4:-1] if c.startswith("enc(") else (c or "")
TXN_500_SURBHI = {"desc": "SURBHI DURGESH GUPTA", "amount": 500.0,
                 "category": "Other", "type": "Expense", "date": "2026-09-16 09:00:00"}
TXN_500_RAHUL = {"desc": "RAHUL SHARMA", "amount": 500.0,
                "category": "Other", "type": "Expense", "date": "2026-09-16 09:00:00"}


@patch("services.document_processing.check_and_alert_anomaly")
@patch("services.document_processing.encrypt_data", side_effect=lambda x: f"enc({x})")
def test_persist_same_amount_date_different_person_not_a_duplicate(_enc, _anomaly):
    """Two different counter-parties with same amount+date+account = two rows."""
    existing = [{
        "amount": 500.0, "transaction_time": "2026-09-16 08:00:00",
        "account_id": "a1", "description": "enc(SURBHI DURGESH GUPTA)",
    }]
    fake = _FakeSupabase(existing)
    res = dp.persist_with_dedup(fake, "u1", "e@e.com", "Test", "a1", "Acc",
                                [TXN_500_RAHUL], decrypt_fn=_decrypt_stub)
    assert res["inserted"] == 1
    assert res["duplicates"] == 0


@patch("services.document_processing.check_and_alert_anomaly")
@patch("services.document_processing.encrypt_data", side_effect=lambda x: f"enc({x})")
def test_persist_same_amount_date_same_person_is_a_duplicate(_enc, _anomaly):
    """A re-scan whose cleaned name is identical IS a duplicate."""
    existing = [{
        "amount": 500.0, "transaction_time": "2026-09-16 08:00:00",
        "account_id": "a1", "description": "enc(SURBHI DURGESH GUPTA)",
    }]
    fake = _FakeSupabase(existing)
    # Noisy UPI string cleans down to the same name -> duplicate.
    txn_from_upi = {"desc": "UPI 004478649026/YESB/SURBHI DURGESH GUPTA/Paid vi",
                    "amount": 500.0, "category": "Other", "type": "Expense",
                    "date": "2026-09-16 09:00:00"}
    res = dp.persist_with_dedup(fake, "u1", "e@e.com", "Test", "a1", "Acc",
                                [txn_from_upi], decrypt_fn=_decrypt_stub)
    assert res["inserted"] == 0
    assert res["duplicates"] == 1


@patch("services.document_processing.check_and_alert_anomaly")
@patch("services.document_processing.encrypt_data", side_effect=lambda x: f"enc({x})")
def test_persist_two_new_same_amount_date_different_people_batch_insert(_enc, _anomaly):
    """One statement that spends ₹500 to two different people inserts both rows."""
    fake = _FakeSupabase([])
    res = dp.persist_with_dedup(fake, "u1", "e@e.com", "Test", "a1", "Acc",
                                [TXN_500_SURBHI, TXN_500_RAHUL])
    assert res["inserted"] == 2
    assert res["duplicates"] == 0
