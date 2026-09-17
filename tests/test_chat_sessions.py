"""
Unit tests for the chat-session persistence (ChatGPT-style history for the
AI CA Advisor) — NO network / Gemini required.

Covers: create/list/rename/delete lifecycle, owner-guarding (a user can never
rename/delete another user's session), the never-throw degradation when the
`chat_sessions` table is missing (migration 004 not run), the backward-
compatible `log_conversation(…, session_id=None)` signature, adding a new
`session_id` to the audit payload, and reconstructing alternating chat turns.

Run with:  python -m pytest tests/test_chat_sessions.py -v
"""
from ai.ca_chatbot import log_conversation
from services.chat_session_service import ChatSessionService, get_chat_session_service

CASCADE = True  # the fake emulates the ON DELETE CASCADE FK for messages


class _Result:
    def __init__(self, data):
        self.data = data


class _Chain:
    """Minimal chainable supabase-py stand-in used by the service methods."""

    def __init__(self, fake, table):
        self.fake, self.table = fake, table
        self.filters = []          # [(col, val)] applied at execute time
        self.order_col = None
        self.order_desc = False
        self.limit_n = None
        self.single = False
        self.op = "select"         # select | insert | update | delete
        self.payload = None

    # ------------------------------------------------------ query builders
    def select(self, _cols=None):
        self.op = "select"
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def order(self, col, desc=False):
        self.order_col = col
        self.order_desc = bool(desc)
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def maybe_single(self):
        self.single = True
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", dict(payload)
        return self

    def update(self, payload):
        self.op, self.payload = "update", dict(payload)
        return self

    def delete(self):
        self.op = "delete"
        return self

    # ------------------------------------------------------------- execute
    def execute(self):
        return self.fake._run(self)


class _FakeSupabase:
    """In-memory tables, honoring eq/order/limit/single like supabase-py."""

    def __init__(self):
        self.tables = {"chat_sessions": [], "ai_conversations": []}
        self._seq = {"chat_sessions": 0}

    def table(self, name):
        if name not in self.tables:
            raise AttributeError(f"no table {name!r} (migration not run)")
        return _Chain(self, name)

    def seed_session(self, user_id, title, session_id="s1"):
        self.tables["chat_sessions"].append({
            "id": session_id, "user_id": user_id, "title": title,
            "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
        })
        return session_id

    def seed_message(self, user_id, session_id, user_message, ai_response):
        self.tables["ai_conversations"].append({
            "id": f"m{len(self.tables['ai_conversations']) + 1}",
            "user_id": user_id, "session_id": session_id,
            "user_message": user_message, "ai_response": ai_response,
            "context": {}, "model": "",
            "created_at": f"2026-01-0{len(self.tables['ai_conversations']) + 1}"
                          f"T00:00:00",
        })

    # ------------------------------------------------------------ internals
    def _run(self, chain):
        rows = self.tables[chain.table]
        if chain.op == "insert":
            row = dict(chain.payload)
            if chain.table == "chat_sessions":
                self._seq[chain.table] += 1
                row["id"] = row.get("id") or f"s{self._seq[chain.table]}"
                row.setdefault("created_at", "2026-01-01T00:00:00")
                row.setdefault("updated_at", "2026-01-01T00:00:00")
            rows.append(row)
            return _Result([row])

        if chain.op == "update":
            for r in rows:
                if all(r.get(k) == v for k, v in chain.filters):
                    r.update(chain.payload)
            return _Result([])

        if chain.op == "delete":
            gone_here = [r for r in rows
                         if all(r.get(k) == v for k, v in chain.filters)]
            self.tables[chain.table] = [r for r in rows if r not in gone_here]
            # Emulate the ON DELETE CASCADE FK: deleting a session wipes its
            # ai_conversations rows too (documenting the migration contract).
            if CASCADE and chain.table == "chat_sessions":
                gone_ids = {r["id"] for r in gone_here}
                self.tables["ai_conversations"] = [
                    r for r in self.tables["ai_conversations"]
                    if r.get("session_id") not in gone_ids]
            return _Result([])

        # select
        out = [dict(r) for r in rows
               if all(r.get(k) == v for k, v in chain.filters)]
        if chain.order_col:
            out.sort(key=lambda r: (r.get(chain.order_col) or ""),
                     reverse=chain.order_desc)
        if chain.limit_n:
            out = out[:chain.limit_n]
        if chain.single:
            return _Result(out[0] if out else None)
        return _Result(out)


class _MissingSupabase:
    """Any table access raises — the migration-004-not-run / offline case."""

    def table(self, _name):
        raise RuntimeError("supabase unavailable — chat_sessions table missing")


MISSING = _MissingSupabase()


# ------------------------------------------------------------------ lifecycle

def test_create_session_and_list():
    fake = _FakeSupabase()
    svc = get_chat_session_service(fake)

    a = svc.create_session("u1", title="Market question")
    b = svc.create_session("u1", title="Tax planning")
    assert a and b
    assert a["title"] == "Market question" and a["user_id"] == "u1"
    assert a["id"] and b["id"] and a["id"] != b["id"]

    sess = svc.list_sessions("u1")
    assert len(sess) == 2


def test_list_sessions_ordered_by_recency():
    fake = _FakeSupabase()
    svc = get_chat_session_service(fake)

    older = svc.create_session("u1", title="Old chat")
    newer = svc.create_session("u1", title="New chat")
    # Usually the newer insert floats up (later updated_at), but touch is the
    # real bump: re-activating the old chat must push it back to the top.
    svc.touch_session("u1", older["id"])
    order = [s["id"] for s in svc.list_sessions("u1")]
    assert order == [older["id"], newer["id"]]


def test_get_session_owner_scoped():
    fake = _FakeSupabase()
    svc = get_chat_session_service(fake)
    sid = fake.seed_session("u1", "Mine", session_id="s1")
    assert svc.get_session("u1", sid) and svc.get_session("u1", sid)["title"] == "Mine"
    assert svc.get_session("u2", sid) is None  # another user can't see it


# ------------------------------------------------------------------ owner guard

def test_cannot_rename_another_users_session():
    fake = _FakeSupabase()
    svc = get_chat_session_service(fake)
    sid = fake.seed_session("u1", "Alice's chat", session_id="s1")

    assert svc.rename_session("u2", sid, "Hijacked") is True   # API returns ok
    # …but the row belongs to u1, so it is untouched under the owner guard.
    assert svc.get_session("u1", sid)["title"] == "Alice's chat"


def test_cannot_delete_another_users_session():
    fake = _FakeSupabase()
    svc = get_chat_session_service(fake)
    sid = fake.seed_session("u1", "Alice's chat", session_id="s1")

    assert svc.delete_session("u2", sid) is True
    assert svc.get_session("u1", sid) is not None  # still there for the owner


def test_rename_session_updates_owner_row():
    fake = _FakeSupabase()
    svc = get_chat_session_service(fake)
    sid = fake.seed_session("u1", "Old title", session_id="s1")
    assert svc.rename_session("u1", sid, "New title") is True
    assert svc.get_session("u1", sid)["title"] == "New title"


# ------------------------------------------------------------------ delete cascade

def test_delete_session_removes_session():
    fake = _FakeSupabase()
    svc = get_chat_session_service(fake)
    sid = fake.seed_session("u1", "Bye", session_id="s1")
    assert svc.delete_session("u1", sid) is True
    assert svc.get_session("u1", sid) is None


def test_delete_session_cascades_messages():
    fake = _FakeSupabase()
    svc = get_chat_session_service(fake)
    sid = fake.seed_session("u1", "With messages", session_id="s1")
    fake.seed_message("u1", sid, "hello", "hi there")
    fake.seed_message("u1", sid, "tax?", "check the planner")

    assert svc.delete_session("u1", sid) is True
    # The session is gone and its ai_conversations rows cascade with it.
    assert svc.get_session("u1", sid) is None
    assert svc.get_messages("u1", sid) == []


# ------------------------------------------------------------------ messages

def test_get_messages_reconstructs_pairs():
    fake = _FakeSupabase()
    svc = get_chat_session_service(fake)
    sid = fake.seed_session("u1", "Chat", session_id="s1")
    fake.seed_message("u1", sid, "What is my XIRR?", "Your XIRR is 12.4%.")
    fake.seed_message("u1", sid, "What about net worth?", "₹12,50,000.")

    turns = svc.get_messages("u1", sid)
    assert [t["role"] for t in turns] == ["user", "assistant",
                                          "user", "assistant"]
    assert turns[0]["content"] == "What is my XIRR?"
    assert turns[1]["content"] == "Your XIRR is 12.4%."
    assert turns[3]["content"] == "₹12,50,000."


def test_get_messages_empty_for_unknown_session():
    fake = _FakeSupabase()
    svc = get_chat_session_service(fake)
    assert svc.get_messages("u1", "no-such-session") == []


# ---------------------------------------------------------- missing table / offline

def test_never_throws_when_tables_missing():
    svc = ChatSessionService(MISSING)
    assert svc.sessions_available() is False
    assert svc.list_sessions("u1") == []
    assert svc.get_session("u1", "s1") is None
    assert svc.get_messages("u1", "s1") == []
    assert svc.create_session("u1", "x") is None
    assert svc.rename_session("u1", "s1", "y") is False
    assert svc.delete_session("u1", "s1") is False
    assert svc.touch_session("u1", "s1") is False


# ------------------------------------------------- log_conversation back-compat

def test_log_conversation_with_session_id():
    fake = _FakeSupabase()
    assert log_conversation(fake, "u1", "hello", "general", {}, "hi",
                            session_id="s1") is True
    row = fake.tables["ai_conversations"][-1]
    assert row["session_id"] == "s1"
    assert row["user_id"] == "u1" and row["user_message"] == "hello"


def test_log_conversation_without_session_id_backcompat():
    fake = _FakeSupabase()
    # Legacy call shape (no session_id) must keep working unchanged.
    assert log_conversation(fake, "u1", "hello", "general", {}, "hi") is True
    row = fake.tables["ai_conversations"][-1]
    assert "session_id" not in row


def test_log_conversation_never_throws_when_table_missing():
    assert log_conversation(MISSING, "u1", "hello", "general", {}, "hi") is False