"""
Chat Session Service — Supabase persistence for the AI CA Advisor's saved
conversations (ChatGPT-style history). Mirrors services/fire_service.py: every
method swallows DB errors into a safe empty value so the page never crashes
when the `chat_sessions` table is missing (migration 004 not yet run) or when
Supabase is unreachable.

One `chat_sessions` row groups the existing `ai_conversations` audit rows (a
nullable `session_id` FK with ON DELETE CASCADE). Deleting a session cascades
to its messages. All writes are owner-guarded (`.eq("user_id", …)`) so a user
can never read / rename / delete another user's conversation — RLS backs this
up too.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from supabase import Client


class ChatSessionService:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    # ------------------------------------------------------------ capability

    def sessions_available(self) -> bool:
        """True when the `chat_sessions` table exists (migration 004 run) and is
        queryable. False when the migration hasn't been applied or Supabase is
        unreachable — the page then degrades to a single unscoped chat instead
        of crashing, exactly like other "run migrations/00N" fallbacks."""
        try:
            self.supabase.table("chat_sessions") \
                .select("id").limit(1).execute()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------ read

    def list_sessions(self, user_id: str, limit: int = 50) -> List[Dict]:
        """The user's conversations, newest activity first."""
        try:
            res = self.supabase.table("chat_sessions") \
                .select("id, title, created_at, updated_at") \
                .eq("user_id", user_id) \
                .order("updated_at", desc=True) \
                .limit(limit).execute()
            return res.data or []
        except Exception:
            return []

    def get_session(self, user_id: str, session_id: str) -> Optional[Dict]:
        """One conversation's metadata — owner-guarded, None if not found."""
        try:
            res = self.supabase.table("chat_sessions") \
                .select("id, title, created_at, updated_at") \
                .eq("id", session_id) \
                .eq("user_id", user_id) \
                .maybe_single().execute()
            return res.data
        except Exception:
            return None

    def get_messages(self, user_id: str, session_id: str) -> List[Dict]:
        """Messages of one session, oldest→newest, reconstructed as alternating
        user/assistant chat turns from the `ai_conversations` audit rows.
        Owner-guarded so one user's session can't leak another's messages."""
        try:
            res = self.supabase.table("ai_conversations") \
                .select("user_message, ai_response, created_at") \
                .eq("user_id", user_id) \
                .eq("session_id", session_id) \
                .order("created_at").execute()
            turns: List[Dict] = []
            for row in res.data or []:
                if row.get("user_message"):
                    turns.append({"role": "user", "content": row["user_message"]})
                if row.get("ai_response"):
                    turns.append({"role": "assistant", "content": row["ai_response"]})
            return turns
        except Exception:
            return []

    # ------------------------------------------------------------ write

    def create_session(self, user_id: str, title: str = "New chat") -> Optional[Dict]:
        """Insert a new empty conversation. Returns the created row."""
        try:
            res = self.supabase.table("chat_sessions") \
                .insert({"user_id": user_id, "title": title}) \
                .execute()
            rows = res.data or []
            return rows[0] if rows else None
        except Exception as e:
            print(f"[chat_session_service] create_session failed: {e}")
            return None

    def rename_session(self, user_id: str, session_id: str, new_title: str) -> bool:
        """Rename one of the user's sessions. Owner-guarded."""
        try:
            self.supabase.table("chat_sessions") \
                .update({"title": (new_title or "New chat")[:200]}) \
                .eq("id", session_id) \
                .eq("user_id", user_id) \
                .execute()
            return True
        except Exception as e:
            print(f"[chat_session_service] rename_session failed: {e}")
            return False

    def touch_session(self, user_id: str, session_id: str) -> bool:
        """Bump a session's updated_at so it floats to the top of the list."""
        try:
            import datetime
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.supabase.table("chat_sessions") \
                .update({"updated_at": now_iso}) \
                .eq("id", session_id) \
                .eq("user_id", user_id) \
                .execute()
            return True
        except Exception as e:
            print(f"[chat_session_service] touch_session failed: {e}")
            return False

    def delete_session(self, user_id: str, session_id: str) -> bool:
        """Permanently delete one conversation (cascade wipes its messages).
        Owner-guarded so it can never remove another user's session."""
        try:
            self.supabase.table("chat_sessions") \
                .delete() \
                .eq("id", session_id) \
                .eq("user_id", user_id) \
                .execute()
            return True
        except Exception as e:
            print(f"[chat_session_service] delete_session failed: {e}")
            return False


def get_chat_session_service(supabase: Client) -> ChatSessionService:
    return ChatSessionService(supabase)