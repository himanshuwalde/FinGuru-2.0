import os
import re
import pandas as pd
from datetime import datetime
import google.generativeai as genai
from utils.ai_persona import persona_and_currency_note
from utils.currency import fmt_money
from utils.email_engine import send_financial_alert
from utils.ai_client import get_gemini_client, get_best_model, generate_content_safe


def _strip_code_fences(text: str) -> str:
    """Strip leading/trailing markdown or triple-quote code fences a model may
    wrap its HTML in (```html … ```, '''html … '''). The email must contain the
    HTML only — no fence markers."""
    if not text:
        return text
    # Opening fence (with optional language tag) at the very start
    text = re.sub(r"(?s)^\s*(?:```|~~~|''')\w*\s*\n?", "", text).strip()
    # Closing fence at the very end
    text = re.sub(r"(?s)\s*(?:```|~~~|''')$", "", text).strip()
    return text


def generate_anomaly_email_content(user_name, account_name, amount, description, date_str, is_temporal, is_behavioral, category_mean):
    """Uses Gemini to draft a high-urgency fraud alert."""
    genai_client = get_gemini_client()
    target_model = get_best_model(genai_client, prefer_flash=True)
    model = genai_client.GenerativeModel(target_model)
    
    reasons = []
    if is_temporal:
        reasons.append("It occurred late at night (between Midnight and 5:00 AM).")
    if is_behavioral:
        reasons.append(f"It is significantly higher than their usual average ({fmt_money(category_mean)}) for this category.")

    prompt = f"""
    {persona_and_currency_note()}

    You are FinGuru's Security AI. You just detected a suspicious transaction for {user_name} on their "{account_name}" account.

    Transaction Details:
    - Merchant: {description}
    - Amount: {fmt_money(amount, dp=2)}
    - Time: {date_str}
    - Why flagged: {' '.join(reasons)}
    
    Task: Draft a short, urgent HTML email body (no <head> or <body> tags, just inner HTML).
    Style it beautifully using inline CSS. Make it look like a professional bank fraud alert.
    Use a soft red/warning color scheme for highlights.
    IMPORTANT: Return ONLY the raw HTML. Do NOT wrap it in code fences, backticks,
    ```html markers, triple single-quotes, or any explanation before or after.
    End with two clear, actionable steps:
    1. If it was them: Tell them they can safely ignore this email.
    2. If it wasn't them: Advise them to open their bank app and freeze their card immediately.
    """
    response = model.generate_content(prompt)
    return _strip_code_fences(response.text)

def check_and_alert_anomaly(supabase, user_id, user_email, user_name, amount, category, description, transaction_time_iso, account_name="Primary Account", exclude_ids=None):
    """Evaluates a single new transaction and triggers an instant email if suspicious.
    `exclude_ids` — ids of the transaction(s) just inserted — are removed from the
    history a behavioral check measures against, so a big new spend isn't masked by
    itself."""
    try:
        # --- 1. TEMPORAL CHECK ---
        # `transaction_time_iso` is a NAIVE local wall-clock string as stored
        # ("2026-09-16 22:00:00"). The app's read-side detector (pages/anomalies.py)
        # treats it exactly as written, and so must we: parsing it as UTC (utc=True)
        # then converting to Asia/Kolkata added +5:30, flagging real 10pm spends as
        # "3:30am" and missing genuine 4am ones. Strip any tz tag WITHOUT shifting.
        txn_time = pd.to_datetime(transaction_time_iso, format="mixed")
        if getattr(txn_time, "tzinfo", None) is not None:
            txn_time = txn_time.tz_localize(None)
        is_temporal_anomaly = 0 <= txn_time.hour <= 5

        # --- 2. BEHAVIORAL CHECK (Z-Score) ---
        is_behavioral_anomaly = False
        category_mean = 0
        
        if amount > 500:
            q = (supabase.table("transactions").select("amount")
                 .eq("user_id", user_id).eq("category", category)
                 .eq("type", "Expense"))
            # Callers insert before evaluating, so exclude the just-created
            # transaction(s) from the history it's measured against — otherwise a
            # big new spend inflates its own mean/std and slips past the flag.
            if exclude_ids:
                q = q.filter("id", "not.in",
                             "(" + ",".join(str(i) for i in exclude_ids) + ")")
            past_txns = q.execute()
            
            if past_txns.data and len(past_txns.data) > 2:
                df = pd.DataFrame(past_txns.data)
                df['amount'] = pd.to_numeric(df['amount'])
                
                category_mean = df['amount'].mean()
                category_std = df['amount'].std()
                if pd.isna(category_std): category_std = 0
                
                if amount > (category_mean + (2 * category_std)):
                    is_behavioral_anomaly = True

        # --- 3. TRIGGER THE EMAIL ---
        if is_temporal_anomaly or is_behavioral_anomaly:
            subject = f"🚨 FRAUD ALERT: Suspicious Transaction on {account_name}"
            
            # Ask Gemini to write the specific body
            html_content = generate_anomaly_email_content(
                user_name, account_name, amount, description, 
                txn_time.strftime("%b %d, %Y at %I:%M %p"), 
                is_temporal_anomaly, is_behavioral_anomaly, category_mean
            )
            
            # Wrap it in your FinGuru master template (Red Header version)
            full_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;">
                <div style="background: linear-gradient(45deg, #e74c3c, #c0392b); padding: 20px; text-align: center; color: white;">
                    <h2 style="margin: 0;">FinGuru Security Alert</h2>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">Account: {account_name}</p>
                </div>
                <div style="padding: 30px; background-color: #ffffff; color: #333333;">
                    {html_content}
                </div>
                <div style="background-color: #f9fafb; padding: 15px; text-align: center; font-size: 12px; color: #6b7280;">
                    Automated Security Guardrail from your FinGuru System.<br>
                </div>
            </div>
            """
            
            send_financial_alert(user_email, subject, full_html)
            print(f"🚨 Anomaly alert fired for {user_email}")
            
    except Exception as e:
        print(f"Failed to run anomaly check: {e}")