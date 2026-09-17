"""
CA Chatbot — the orchestrator for the grounded financial assistant.

Pipeline (all deterministic except the final explanation):
  user_message → intent_router.route_intent()
               → context_builder.run_tools(needed tools from engine outputs)
               → prompts.build_prompt(user_message, grounding, history)
               → utils.ai_client (Gemini) → grounded reply
               → (fallback) prompts.deterministic_answer when AI is offline

Gemini is used ONLY to explain already-computed figures; every number in the
reply is grounded in the JSON we send. The chat is logged for audit in the
`ai_conversations` table by the page (ai_advisor.py).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from supabase import Client

from ai.context_builder import run_tools, serialize_results
from ai.intent_router import INTENT_TOOLS, route_intent
from ai.prompts import build_prompt, deterministic_answer
from utils.ai_persona import build_persona_block
from utils.currency import ai_currency_note


def respond(supabase: Client, user_id: str,
            user_message: str,
            history: Optional[List[Dict]] = None) -> Tuple[str, str, Dict]:
    """
    Returns (reply_text, intent, grounding_dict, used_ai). `used_ai` is True
    when Gemini produced the reply and False when it fell back to the
    deterministic answer (no API key, quota exceeded, network error).
    Never raises: any failure degrades to the deterministic offline answer.
    """
    history = history or []
    intent = route_intent(user_message)
    tool_names = INTENT_TOOLS.get(intent, [])

    results = run_tools(supabase, user_id, tool_names)
    grounding = serialize_results(results)

    # Strict per-user persona + currency instructions injected before the data.
    persona_block = build_persona_block()
    currency_note = ai_currency_note()

    try:
        from utils.ai_client import (get_gemini_client, get_generative_model,
                                     generate_content_safe)
        genai = get_gemini_client()
        model = get_generative_model(genai, prefer_flash=True)
        prompt = build_prompt(user_message, grounding, history,
                              persona_block=persona_block,
                              currency_note=currency_note)
        text = generate_content_safe(model, prompt, max_retries=1)
    except Exception as e:
        print(f"[ca_chatbot] AI call failed ({e}); using deterministic fallback")
        text = None

    used_ai = bool(text and text.strip())
    if not used_ai:
        text = deterministic_answer(intent, results)

    return text.strip(), intent, results, used_ai


def log_conversation(supabase: Client, user_id: str, user_message: str,
                     intent: str, grounding: Dict, ai_response: str,
                     session_id: Optional[str] = None) -> bool:
    """Persist one chat exchange to `ai_conversations` (used by ai_advisor).

    `session_id` is the optional chat session this exchange belongs to; when
    present it links the audit row to a saved conversation. Backward
    compatible: legacy callers that omit it keep inserting ungrouped rows.
    """
    try:
        import json
        typical = ["tax", "tax_saving", "portfolio", "net_worth", "fire",
                   "spending", "market", "advice", "general"]
        summary = {"intent": intent}
        for k, v in grounding.items():
            if k in typical and isinstance(v, dict) and v.get("status") == "ok":
                summary[k] = _shorten(v)
        payload = {
            "user_id": user_id,
            "user_message": user_message[:2000],
            "context": json.dumps(summary, default=float)[:8000],
            "ai_response": ai_response[:4000],
            "model": "",
        }
        if session_id:
            payload["session_id"] = session_id
        supabase.table("ai_conversations").insert(payload).execute()
        return True
    except Exception as e:
        print(f"[ca_chatbot] log_conversation failed: {e}")
        return False


def _shorten(d: object) -> object:
    """Compact grounding for storage — keep the headline numbers, drop noise."""
    if isinstance(d, dict):
        keep = {}
        for k, v in d.items():
            if isinstance(v, list) and len(v) > 3:
                keep[k] = v[:3]
            elif isinstance(v, (dict, list)):
                keep[k] = _shorten(v)
            else:
                keep[k] = v
        return keep
    if isinstance(d, list):
        return [_shorten(x) for x in d[:6]]
    return d