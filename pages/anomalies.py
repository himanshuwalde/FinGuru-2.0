import streamlit as st
import pandas as pd
import numpy as np
from utils.ai_persona import persona_and_currency_note
from utils.security import decrypt_data
from utils.currency import fmt_money, to_display
from utils.ai_client import get_gemini_client, get_best_model, generate_content_safe

# Initialize AI client
genai_client = get_gemini_client()

def render_page(supabase):
    st.markdown("""
        <div class="page-header">
            <h2>Anomaly Finder</h2>
            <p>We monitor your accounts for unusual patterns, late-night swipes, and behavioral anomalies.</p>
        </div>
    """, unsafe_allow_html=True)

    # --- 1. FETCH DATA ---
    try:
        # Fetch transactions
        trans_res = supabase.table("transactions").select("*").eq("user_id", st.session_state.user_id).execute()
        transactions = trans_res.data
        
        # Fetch accounts to get the readable account names
        acc_res = supabase.table("accounts").select("id, account_name").eq("user_id", st.session_state.user_id).execute()
        accounts = acc_res.data
        
        # Create a quick dictionary to map account_id -> account_name
        account_map = {acc['id']: acc['account_name'] for acc in accounts} if accounts else {}

    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        return

    if not transactions:
        st.info("Log some transactions first so we can learn your normal spending behavior!")
        return

    df = pd.DataFrame(transactions)
    df = df.drop_duplicates(subset='id', keep='first')
    df['amount'] = pd.to_numeric(df['amount'])
    
    # Map the account names into the dataframe
    df['account_name'] = df['account_id'].map(account_map).fillna('Unknown Account')
    
    # ✨ THE FIX 1: Read the exact database time and strip the timezone tag WITHOUT shifting the hours
    df['transaction_time'] = pd.to_datetime(df['transaction_time'], format='mixed')
    if df['transaction_time'].dt.tz is not None:
        df['transaction_time'] = df['transaction_time'].dt.tz_localize(None)

    # Decrypt the description column so the UI and AI get the readable names
    df['description'] = df['description'].apply(lambda x: decrypt_data(str(x)) if pd.notnull(x) else "")

    # Drop duplicate *content* (same time, amount, merchant, account) — double-clicked
    # Save or a re-run sync can insert the same spend twice with different ids.
    df = df.drop_duplicates(
        subset=['transaction_time', 'amount', 'description', 'account_id', 'type'],
        keep='first',
    )

    # We only care about checking Expenses for anomalies, not Income
    expenses_df = df[df['type'] == 'Expense'].copy()

    if expenses_df.empty:
        st.info("No expenses found to audit yet.")
        return

    with st.spinner("Running statistical analysis on your transaction history..."):
        
        # --- 2. TEMPORAL ANOMALY DETECTION ---
        # Flag anything bought between Midnight (0) and 5 AM (Now accurately using the raw DB time!)
        expenses_df['hour'] = expenses_df['transaction_time'].dt.hour
        expenses_df['is_temporal_anomaly'] = (expenses_df['hour'] >= 0) & (expenses_df['hour'] <= 5)

        # --- 3. BEHAVIORAL ANOMALY DETECTION (Z-SCORE) ---
        # Calculate the Mean and Standard Deviation for EACH category
        category_stats = expenses_df.groupby('category')['amount'].agg(['mean', 'std']).reset_index()
        category_stats['std'] = category_stats['std'].fillna(0) # Handle single-transaction categories
        
        expenses_df = expenses_df.merge(category_stats, on='category', how='left')
        
        # The Math: Is the amount > (Mean + 2 * Standard Deviation)?
        # We also add a baseline (> ₹500) so a ₹50 coffee isn't flagged just because the average is ₹10.
        expenses_df['is_behavioral_anomaly'] = (expenses_df['amount'] > (expenses_df['mean'] + (2 * expenses_df['std']))) & (expenses_df['amount'] > 500)

        # --- 4. FILTER THE OUTLIERS ---
        anomalies = expenses_df[(expenses_df['is_temporal_anomaly']) | (expenses_df['is_behavioral_anomaly'])].copy()

    # Most recent transactions first
    anomalies = anomalies.sort_values('transaction_time', ascending=False)

    # --- 5. THE UI DASHBOARD ---
    st.write("---")
    
    if anomalies.empty:
        st.success("✅ Good news! All your recent transactions look perfectly normal based on your historical behavior.")
        return

    st.warning(f"⚠️ We found {len(anomalies)} unusual transactions that require your attention.")
    
    # --- 6. AI AUDIT REPORT ---
    st.write("")
    st.subheader("🤖 Security & Audit Note")
    
    # ✨ THE FIX 2: Convert Pandas Timestamps to normal strings so the Gemini API doesn't crash!
    safe_anomalies = anomalies.copy()
    safe_anomalies['transaction_time'] = safe_anomalies['transaction_time'].astype(str)
    # Amounts are stored in INR — re-express in the display currency for the AI.
    safe_anomalies['amount'] = safe_anomalies['amount'].apply(to_display)
    anomaly_summary = safe_anomalies[['transaction_time', 'description', 'category', 'amount', 'account_name', 'is_behavioral_anomaly', 'is_temporal_anomaly']].to_dict('records')
    
    # Initialize the session state properly if it doesn't exist
    if 'audit_report' not in st.session_state:
        st.session_state.audit_report = None
        
    if st.session_state.audit_report:
        st.info(st.session_state.audit_report)
        if st.button("🔄 Regenerate Report"):
            st.session_state.audit_report = None
            st.rerun()
    else:
        if st.button("Ask AI to Analyze These Outliers", type="primary"):
            with st.spinner("AI is reviewing the flagged transactions..."):
                try:
                    target_model = get_best_model(genai_client, prefer_flash=True)
                    model = genai_client.GenerativeModel(target_model)

                    prompt = f"""
                    {persona_and_currency_note()}

                    You are an expert fraud analyst and financial auditor. I used statistical Z-scores and time-bounds to flag these unusual transactions:
                    {anomaly_summary}

                    Write a brief, professional warning message to the user. Explain *why* these specific transactions are flagged (e.g., late night, or higher than their usual category average). Because the data now includes 'account_name', be sure to mention which bank account is at risk. Give them one actionable piece of advice (like 'verify with your bank' or 'freeze your card if unrecognized').
                    Keep it short, direct, and do not use markdown bolding.
                    """

                    response_text = generate_content_safe(model, prompt)

                    if response_text:
                        st.session_state.audit_report = response_text
                        st.rerun()
                    else:
                        raise Exception("Empty response from model")

                except Exception as e:
                    print(f"AI Audit Error: {e}")
                    fallback = "These transactions fall significantly outside your historical spending patterns or occurred during unusual hours. Please review them carefully. If you do not recognize these charges, contact your bank immediately to secure your account."
                    st.session_state.audit_report = fallback
                    st.rerun()

    # Visual Box for the List
    with st.container(border=True):
        st.subheader("Suspicious Transactions")
        
        # Draw the rows
        for _, row in anomalies.iterrows():
            date_str = row['transaction_time'].strftime("%b %d, %Y at %I:%M %p")
            desc = str(row['description']).title()
            amt = fmt_money(row['amount'], dp=2)
            acc_name = row['account_name'] 
            
            tags = ""
            if row['is_behavioral_anomaly']:
                avg = fmt_money(row['mean'])
                tags += f"<span style='background: rgba(231, 76, 60, 0.1); color: #e74c3c; border: 1px solid rgba(231, 76, 60, 0.2); padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; margin-right: 8px;'>💰 Unusual Amount (Usually {avg})</span>"
            if row['is_temporal_anomaly']:
                tags += f"<span style='background: rgba(59, 130, 246, 0.1); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.2); padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600;'>🌙 Late Night Swipe</span>"

            # ✨ THE FIX 3: Indented this block so it repeats for EVERY row, not just the last one!
            st.markdown(f"""
            <div style='padding: 15px 10px; border-bottom: 1px solid rgba(150,150,150,0.2);'>
                <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;'>
                    <strong style='font-size: 1.15rem; color: var(--text-color);'>{desc}</strong>
                    <strong style='color: #e74c3c; font-size: 1.2rem;'>{amt}</strong>
                </div>
                <div style='color: var(--text-color); opacity: 0.6; font-size: 0.85rem; margin-bottom: 10px; font-weight: 500;'>{date_str} • {row['category']} • 🏦 {acc_name}</div>
                <div>{tags}</div>
            </div>
            """, unsafe_allow_html=True)