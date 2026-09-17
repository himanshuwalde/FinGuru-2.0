"""
AI CA Chatbot page — "CA Guru", the hybrid financial assistant.
Answers your own numbers (tax, net worth, portfolio, FIRE, spending) from
computed engine outputs, and gives general educational financial guidance for
everything else — market trends, saving tips, investment decisions. Live market
data (NIFTY, Sensex, Gold) is fetched in real time. If Gemini is unavailable a
deterministic offline answer is shown. Every exchange is logged to
`ai_conversations`, and conversations are saved to `chat_sessions` so you can
re-open, rename, or delete them — history on the left, current chat on the right.
"""
from __future__ import annotations

import json

import streamlit as st

import ai.ca_chatbot as ca_chatbot
from ai.intent_router import TOOL_DESCRIPTIONS
from services.chat_session_service import get_chat_session_service
from utils.ui_components import render_gradient_header


@st.dialog("Clear conversation")
def confirm_clear_conversation():
    """Ask before wiping the in-session CA chat history (single-chat fallback)."""
    st.warning("Clear this conversation? The chat history will be wiped.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, clear", type="primary", use_container_width=True):
        st.session_state.ca_messages = []
        st.rerun()
    if c2.button("Cancel", use_container_width=True):
        st.rerun()


@st.dialog("Rename chat")
def confirm_rename_session(svc, user_id, session):
    """Rename one saved conversation (owner-guarded)."""
    st.text_input("Chat title", value=session.get("title") or "New chat",
                  key="_rename_title")
    c1, c2 = st.columns(2)
    if c1.button("Save", type="primary", use_container_width=True):
        new_title = (st.session_state.get("_rename_title") or "New chat").strip()
        if svc.rename_session(user_id, session["id"], new_title):
            st.session_state.ca_refresh_sessions = True
            if st.session_state.ca_active_session_id == session["id"]:
                st.session_state.ca_active_session_title = new_title
            st.rerun()
        else:
            st.error("Couldn't rename — try again.")
    if c2.button("Cancel", use_container_width=True):
        st.rerun()


@st.dialog("Delete chat")
def confirm_delete_session(svc, user_id, session):
    """Confirm before permanently deleting a saved conversation and its messages."""
    st.warning("Delete this conversation? All its messages will be "
               "permanently removed. This cannot be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, delete", type="primary", use_container_width=True):
        if svc.delete_session(user_id, session["id"]):
            if st.session_state.ca_active_session_id == session["id"]:
                st.session_state.ca_messages = []
                st.session_state.ca_grounding = {}
                st.session_state.ca_active_session_id = None
                st.session_state.ca_active_session_title = None
            st.session_state.ca_refresh_sessions = True
            st.rerun()
        else:
            st.error("Couldn't delete — the conversation may already be gone.")
    if c2.button("Cancel", use_container_width=True):
        st.rerun()


def _init_chat_state():
    """Make sure every chat-session key exists (first render of the page)."""
    defaults = {
        "ca_messages": [],
        "ca_grounding": {},
        "ca_sessions": [],
        "ca_active_session_id": None,
        "ca_active_session_title": None,
        "ca_refresh_sessions": True,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _open_session(svc, user_id, sid, title):
    """Load one saved conversation's full history into the chat view."""
    st.session_state.ca_messages = svc.get_messages(user_id, sid) or []
    st.session_state.ca_grounding = {}
    st.session_state.ca_active_session_id = sid
    st.session_state.ca_active_session_title = title


def _render_session_sidebar(svc, user_id):
    """Left panel: new chat + the list of saved conversations with rename/delete."""
    st.markdown("##### 💬 Chat history")
    if st.button("➕ New chat", use_container_width=True):
        st.session_state.ca_messages = []
        st.session_state.ca_grounding = {}
        st.session_state.ca_active_session_id = None
        st.session_state.ca_active_session_title = None
        st.rerun()

    sessions = st.session_state.get("ca_sessions") or []
    if not sessions:
        st.caption("No saved chats yet — send your first message and it "
                   "will appear here.")
    active_id = st.session_state.ca_active_session_id
    for s in sessions:
        sid = s.get("id")
        title = s.get("title") or "New chat"
        is_active = (sid == active_id)
        prefix = "● " if is_active else ""
        row = st.columns([0.62, 0.19, 0.19])
        if row[0].button(f"{prefix}{title}", key=f"open_{sid}",
                         use_container_width=True,
                         help="Open this conversation"):
            _open_session(svc, user_id, sid, title)
        if row[1].button("✏️", key=f"ren_{sid}", help="Rename chat"):
            confirm_rename_session(svc, user_id, s)
        if row[2].button("🗑", key=f"del_{sid}", help="Delete chat"):
            confirm_delete_session(svc, user_id, s)


def _render_bottom_controls(svc, user_id, sessions):
    """After the chat: clear/delete the conversation + show the grounding used."""
    st.write("---")
    if not st.session_state.ca_messages:
        return
    c1, c2 = st.columns(2)
    with c1:
        active_id = st.session_state.ca_active_session_id
        if sessions and active_id:
            session = {"id": active_id,
                       "title": st.session_state.ca_active_session_title}
            if st.button("🗑 Delete this conversation", use_container_width=True):
                confirm_delete_session(svc, user_id, session)
        elif not sessions:
            if st.button("🗑 Clear conversation", use_container_width=True):
                confirm_clear_conversation()
    with c2:
        with st.expander("See the grounding data this session used"):
            st.json(json.dumps({k: v for k, v in
                                st.session_state.ca_grounding.items()},
                               default=float)[:6000])


def render_page(supabase):
    render_gradient_header(
        "🧑‍💼", "AI CA Advisor",
        "Personalized tax, portfolio & FIRE guidance from your data — plus general "
        "financial education. Always grounded in real numbers, never makes it up.",
        gradient_colors=["#0EA5E9", "#8B5CF6"],
    )
    st.write("---")

    intro = st.columns([2, 1])
    with intro[0]:
        st.markdown(
            "**How it works:** your numbers come from FinGuru's deterministic "
            "engines; Gemini explains them. For general questions (market updates, "
            "investment decisions, saving tips) it provides educational guidance — "
            "never inventing specific prices. Live market data (NIFTY, Sensex, Gold) "
            "is fetched in real time. If no AI key is set, you still get a "
            "numbers-first answer. **Your past chats are saved and listed on the "
            "left — rename or delete them anytime.**")
    with intro[1]:
        with st.expander("What can it answer?"):
            for name, desc in TOOL_DESCRIPTIONS.items():
                st.markdown(f"- **{name}** — {desc}")

    _init_chat_state()
    svc = get_chat_session_service(supabase)
    user_id = st.session_state.get("user_id")

    # Migration 004 not run: keep the current single-chat behavior. The chat
    # input renders here at the page's top level, so it stays pinned to the
    # bottom of the app (see _render_chat).
    if not svc.sessions_available():
        st.info("⚠️ **Chat history needs one more migration.** Run "
                "`migrations/004_chat_sessions.sql` in the Supabase SQL editor "
                "to enable saved conversations (re-open / rename / delete). "
                "The chat below works normally — it just isn't saved into "
                "history you can come back to.")
        _render_chat(supabase, user_id, svc, sessions=False, with_input=True)
        return

    if st.session_state.ca_refresh_sessions:
        st.session_state.ca_sessions = svc.list_sessions(user_id)
        st.session_state.ca_refresh_sessions = False

    left, right = st.columns([1, 2.4], gap="medium")
    with left:
        _render_session_sidebar(svc, user_id)
    with right:
        reply_spot = _render_chat(supabase, user_id, svc, sessions=True,
                                  with_input=False)

    # Pinned chat input — Streamlit docks st.chat_input to the very bottom of
    # the app only when it is a top-level element. Inside a column (as before)
    # it stayed inline in the flow and floated above the newest reply. So the
    # input is read here, after the columns; the new exchange renders into
    # `reply_spot` (still inside the right panel, above the pinned input).
    pending = st.session_state.pop("_pending_chip", None)
    prompt = pending or st.chat_input("e.g. How can I save tax this year?")
    if prompt:
        _handle_prompt(supabase, user_id, svc, prompt, reply_spot,
                       sessions=True)


def _handle_prompt(supabase, user_id, svc, prompt, reply_spot, sessions):
    """Run the engine → render the user+assistant exchange into `reply_spot` →
    persist it (audit row + saved conversation). `sessions` enables lazy session
    creation on the first message (title from the opening words, like ChatGPT).

    Rendering into `reply_spot` keeps the newest exchange directly under the
    history and ABOVE the pinned chat input, even though the input was read
    after this container was created."""
    # Lazy session creation: the first message becomes the saved chat.
    session_id = st.session_state.ca_active_session_id
    if sessions and not session_id:
        created = svc.create_session(user_id, title=prompt[:40])
        if created and created.get("id"):
            session_id = created["id"]
            st.session_state.ca_active_session_id = session_id
            st.session_state.ca_active_session_title = \
                created.get("title") or prompt[:40]
            st.session_state.ca_refresh_sessions = True

    reply_spot.chat_message("user", avatar="👤").markdown(prompt)
    st.session_state.ca_messages.append({"role": "user", "content": prompt})

    with reply_spot.chat_message("assistant", avatar="🧑‍💼"):
        placeholder = st.empty()
        with st.spinner("Reading your computed numbers…"):
            reply, intent, grounding, used_ai = ca_chatbot.respond(
                supabase, user_id, prompt, st.session_state.ca_messages[:-1])

        placeholder.markdown(reply)
        st.session_state.ca_messages.append({"role": "assistant", "content": reply})
        st.session_state.ca_grounding[intent] = grounding

        if not used_ai:
            st.caption("The AI model is unavailable right now — showing a "
                       "numbers-first answer from your data instead.")
        # intent badge + audit trail
        st.caption(f"intent → `{intent}`")
    if not ca_chatbot.log_conversation(supabase, user_id, prompt,
                                       intent, grounding, reply,
                                       session_id=session_id):
        st.caption("(chat history not persisted — `ai_conversations` table missing)")
    if session_id:
        svc.touch_session(user_id, session_id)


def _render_chat(supabase, user_id, svc, sessions, with_input):
    """Shared chat body: session title + chips + full message history + bottom
    controls + disclaimer. A `reply_spot` container for the current submission's
    new messages is created right after the history so they render directly
    under it — ABOVE the chat input, even though the input is read later.

    `with_input=True` renders st.chat_input here — used by the single-chat
    fallback where the page body has no column, so the input is a top-level
    element and Streamlit pins it to the bottom of the app. The two-panel
    layout calls us with `with_input=False` from inside a column and reads
    st.chat_input at the page's top level instead — inside a column the input
    stays inline in the flow and floats above newer replies."""
    if sessions and st.session_state.ca_active_session_title:
        st.markdown(f"###### {st.session_state.ca_active_session_title}")

    # ---- quick-suggestion chips ------------------------------------------------
    st.markdown("##### 💡 Try asking")
    chip_cols = st.columns(4)
    _chips = [
        "What's the current market update?",
        "Should I buy a stock?",
        "How can I save tax?",
        "How to save money every month?",
    ]
    for _col, _chip in zip(chip_cols, _chips):
        if _col.button(_chip, key=f"chip_{_chip[:20]}", use_container_width=True):
            st.session_state["_pending_chip"] = _chip
            st.rerun()

    # ------------------------------------------------------------ chat body
    for msg in st.session_state.ca_messages:
        with st.chat_message(msg["role"],
                             avatar="🧑‍💼" if msg["role"] == "assistant" else "👤"):
            st.markdown(msg["content"])

    # New messages from the current submission land here — under the history,
    # above the controls, and before the pinned chat input in the DOM.
    reply_spot = st.container()

    prompt = None
    if with_input:
        # Chips populate _pending_chip; regular input falls through naturally.
        pending = st.session_state.pop("_pending_chip", None)
        prompt = pending or st.chat_input("e.g. How can I save tax this year?")

    _render_bottom_controls(svc, user_id, sessions)

    st.caption("⚠️ FinGuru provides educational information, not SEBI-registered "
               "investment, tax, or legal advice. Consult a qualified professional "
               "before making financial decisions. Past performance ≠ future results.")

    if with_input and prompt:
        _handle_prompt(supabase, user_id, svc, prompt, reply_spot, sessions)

    return reply_spot