"""Tests for utils/anomaly_engine.py — temporal naive/aware regression + behavioural self-exclusion."""
import pandas as pd
from utils import anomaly_engine as ae

# ---------------------------------------------------------------------------
# Fakes — mirror the supabase query chain the engine calls
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rows):
        self.data = rows


class _FakeTbl:
    """Chainable fake for .select().eq().eq().filter().execute()"""

    def __init__(self, rows):
        self._rows = list(rows)

    def select(self, *cols):
        return self

    def eq(self, col, value):
        return self

    def filter(self, col, op, value):
        if op == "not.in":
            ids = {x.strip() for x in value.strip("()").split(",") if x.strip()}
            self._rows = [r for r in self._rows if str(r.get("id")) not in ids]
        return self

    def execute(self):
        return _FakeResult(self._rows)


class _FakeSupabase:
    def __init__(self, rows):
        self._rows = rows

    def table(self, name):
        return _FakeTbl(self._rows)


def _fire(rows=None, **kw):
    """Run check_and_alert_anomaly with stubbed email side-effects.

    Returns the list of recipient emails the alert was sent to (empty = no flag).
    """
    sent = []
    ae.generate_anomaly_email_content = lambda *_a, **_k: "<html/>"
    ae.send_financial_alert = lambda email, *_a, **_k: sent.append(email)

    defaults = dict(
        supabase=_FakeSupabase(rows or []),
        user_id="u1",
        user_email="user@example.com",
        user_name="Test",
        amount=100,
        category="Dining",
        description="Big Night",
        transaction_time_iso="2026-09-16 14:00:00",
    )
    defaults.update(kw)
    ae.check_and_alert_anomaly(**defaults)
    return sent


# ---------------------------------------------------------------------------
# EMAIL CONTENT — model-made HTML must not leak code fences into the email
# ---------------------------------------------------------------------------

def test_strip_code_fences_backtick_html():
    assert ae._strip_code_fences("```html\n<div>Alert</div>\n```") == "<div>Alert</div>"


def test_strip_code_fences_backtick_no_lang():
    assert ae._strip_code_fences("```\n<p>Hi</p>\n```") == "<p>Hi</p>"


def test_strip_code_fences_triple_single_quote():
    assert ae._strip_code_fences("'''html\n<b>Fraud</b>\n'''") == "<b>Fraud</b>"


def test_strip_code_fences_untouched_fenced_html():
    # No fence at all -> returned unchanged
    assert ae._strip_code_fences("<div>Plain</div>") == "<div>Plain</div>"


# ---------------------------------------------------------------------------
# TEMPORAL — naive wall-clock must NOT be shifted +5:30
# ---------------------------------------------------------------------------

def test_naive_4am_flagged():
    assert len(_fire(transaction_time_iso="2026-09-16 04:00:00")) == 1


def test_naive_10pm_not_flagged():
    """Regression: old code parsed as UTC then converted to IST, flipping a real
    10 pm spend into 3:30 am and firing a false alert."""
    assert len(_fire(transaction_time_iso="2026-09-16 22:00:00")) == 0


def test_aware_ist_4am_flagged():
    """Webhook sends '…04:00:00+05:30'; hour must read 4, not 9:30."""
    assert len(_fire(transaction_time_iso="2026-09-16T04:00:00+05:30")) == 1


def test_aware_ist_10pm_not_flagged():
    assert len(_fire(transaction_time_iso="2026-09-16T22:00:00+05:30")) == 0


def test_afternoon_never_flagged():
    assert len(_fire(transaction_time_iso="2026-09-16 14:00:00")) == 0


# ---------------------------------------------------------------------------
# BEHAVIORAL — just-inserted txn must be excluded from history
# ---------------------------------------------------------------------------

_PAST = [{"id": i, "amount": a} for i, a in enumerate([100, 120, 140])]


def test_self_exclusion_masks_without_flag():
    """With the new big txn included in history it masks itself → no flag."""
    rows = list(_PAST) + [{"id": 999, "amount": 9999}]
    assert len(_fire(rows=rows, amount=9999)) == 0


def test_self_exclusion_flags_when_excluded():
    """With the new txn excluded it's measured against 3 modest ones → flagged."""
    rows = list(_PAST) + [{"id": 999, "amount": 9999}]
    assert len(_fire(rows=rows, amount=9999, exclude_ids=[999])) == 1


def test_batch_exclude_many_ids():
    """Batch inserts pass every new id."""
    rows = list(_PAST) + [{"id": 10, "amount": 9999}, {"id": 11, "amount": 8000}]
    assert len(_fire(rows=rows, amount=9999, exclude_ids=[10, 11])) == 1


def test_moderate_increase_not_flagged():
    rows = [{"id": i, "amount": a} for i, a in enumerate([200, 210, 220])]
    assert len(_fire(rows=rows, amount=225)) == 0


def test_amount_gate_skips_below_500():
    rows = [{"id": i, "amount": 10} for i in range(10)]
    assert len(_fire(rows=rows, amount=100)) == 0
    assert len(_fire(rows=rows, amount=600)) == 1
