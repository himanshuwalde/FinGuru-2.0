import streamlit as st
import datetime
from PIL import Image
import json
import re
import pandas as pd
from utils.security import encrypt_data
from utils.currency import fmt_input_label, fmt_label, fmt_money, to_inr
from utils.anomaly_engine import check_and_alert_anomaly
from utils.ai_client import get_gemini_client, get_best_model, generate_content_safe

# Initialize AI client
genai_client = get_gemini_client()

def render_page(supabase):
    
    # ✨ THE FIX: Replaced hardcoded gradient/colors with dynamic theme variables
    st.markdown("""
    <style>
        [data-testid="stFileUploader"] {
            padding: 1.5rem;
            background-color: var(--secondary-background-color);
            border-radius: 12px;
            color: var(--text-color);
            text-align: center;
            border: 2px dashed var(--primary-color);
            transition: all 0.3s ease;
            opacity: 0.9;
        }
        [data-testid="stFileUploader"]:hover {
            border-color: var(--text-color);
            opacity: 1.0;
        }
        [data-testid="stFileUploader"] section {
            color: var(--text-color) !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # --- ✨ THE FIX: Cancel/Back drops the hidden screen overlay ---
    def exit_form():
        if 'editing_transaction_data' in st.session_state:
            del st.session_state.editing_transaction_data
        st.session_state.force_page = None

    is_editing = 'editing_transaction_data' in st.session_state
    
    # Header with a slick Back button
    h_col1, h_col2 = st.columns([4, 1])
    with h_col1:
        if is_editing:
            st.title("✏️ Editing Transaction")
            editing_data = st.session_state.editing_transaction_data
            st.markdown(f"You are modifying the transaction logged on **{pd.to_datetime(editing_data['transaction_time']).strftime('%b %d, %Y')}**.")
        else:
            st.title("📝 Add Transaction")
            st.caption(f"🔧 Diagnostic: GenAI Library Version {genai_client.__version__}")
    with h_col2:
        st.write("")
        st.button("← Back", use_container_width=True, on_click=exit_form)
        
    try:
        acc_response = supabase.table("accounts").select("*").eq("user_id", st.session_state.user_id).execute()
        user_accounts = acc_response.data
    except Exception as e:
        st.error("Failed to fetch accounts.")
        user_accounts = []

    if len(user_accounts) == 0:
        st.warning("⚠️ You need to add a Bank Account in the Dashboard before logging a transaction!")
        return

    account_dict = {acc['account_name']: acc['id'] for acc in user_accounts}
    account_names = list(account_dict.keys())
    
    primary_idx = 0
    for i, acc in enumerate(user_accounts):
        if acc.get('is_primary'):
            primary_idx = i
            break
            
    base_categories = ["Food & Dining", "Transport", "Shopping", "Entertainment", "Groceries", "Utilities", "Income", "Education", "Other"]

    if 'trans_amount' not in st.session_state: 
        st.session_state.trans_amount = float(editing_data['amount']) if is_editing else 0.0
    if 'trans_desc' not in st.session_state: 
        st.session_state.trans_desc = str(editing_data['description']) if is_editing else ""
    if 'trans_date' not in st.session_state: 
        st.session_state.trans_date = pd.to_datetime(editing_data['transaction_time']).date() if is_editing else datetime.date.today()
    if 'trans_category' not in st.session_state: 
        st.session_state.trans_category = str(editing_data['category']) if is_editing else "Other"
    if 'trans_type' not in st.session_state: 
        st.session_state.trans_type = str(editing_data['type']) if is_editing else "Expense"
    if 'trans_account_name' not in st.session_state: 
        if is_editing:
            acc_id_to_edit = editing_data['account_id']
            acc_name_to_edit = next((acc['account_name'] for acc in user_accounts if acc['id'] == acc_id_to_edit), None)
            st.session_state.trans_account_name = acc_name_to_edit or account_names[primary_idx]
        else:
            st.session_state.trans_account_name = account_names[primary_idx]
    if 'trans_recurring' not in st.session_state: 
        st.session_state.trans_recurring = bool(editing_data.get('is_recurring')) if is_editing else False

    # Use centralized model selection
    target_model = get_best_model(genai_client, prefer_flash=True)
    model = genai_client.GenerativeModel(target_model)

    if not is_editing:
        st.write("---")
        uploaded_file = st.file_uploader("📸 Scan Receipt with AI", type=["jpg", "jpeg", "png"])

        if uploaded_file is not None and st.button("Extract Data", use_container_width=True):
            with st.spinner(f"🧠 Multimodal AI ({target_model}) analyzing layout and text..."):
                try:
                    image = Image.open(uploaded_file)

                    prompt = f"""
                    Extract data from this receipt. Use EXACTLY these JSON keys:
                    "merchant": string, name of the store.
                    "amount": float, final total (numbers only).
                    "date": string, YYYY-MM-DD format (or null).
                    "category": string, MUST be exactly one of these: {base_categories}. Guess the best fit based on the merchant.
                    """

                    response = model.generate_content(
                        [prompt, image],
                        generation_config=genai_client.GenerationConfig(response_mime_type="application/json")
                    )

                    extracted_data = json.loads(response.text)

                    extracted_desc = str(extracted_data.get("merchant", "")).title()
                    raw_amount = str(extracted_data.get("amount", "0"))
                    clean_amount = float(re.sub(r'[^\d.]', '', raw_amount) or "0")
                    extracted_category = extracted_data.get("category", "Other")
                    extracted_date = datetime.date.today()
                    try:
                        date_str = extracted_data.get("date")
                        if date_str:
                            extracted_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    except Exception:
                        pass

                    st.session_state.trans_amount = clean_amount
                    st.session_state.trans_desc = extracted_desc
                    st.session_state.trans_category = extracted_category
                    st.session_state.trans_date = extracted_date

                    st.success("✅ Receipt successfully scanned!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Failed to process receipt: {e}")
                    
    st.write("---")

    with st.container():
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.selectbox("Type", ["Expense", "Income"], key="trans_type")
            amount = st.number_input(fmt_input_label("Amount"), min_value=0.0, step=10.0, key="trans_amount")
            date = st.date_input("When? (Date)", key="trans_date")
            st.write("") 
            is_recurring = st.toggle("🔁 Monthly Recurring", key="trans_recurring")
            
        with col2:
            account_name = st.selectbox("Where? (Account)", account_names, key="trans_account_name")
            description = st.text_input("Description (e.g., 'Netflix')", key="trans_desc")
            
            if st.button("✨ Auto-Categorize", use_container_width=True):
                if description:
                    with st.spinner("Asking Gemini..."):
                        try:
                            # Use the same model for text (flash models handle both vision and text well)
                            text_model = genai_client.GenerativeModel(target_model)
                            prompt = f"Categorize the transaction '{description}' into EXACTLY one of these categories: {base_categories}. Return ONLY the exact category name as pure text, nothing else."

                            response_text = generate_content_safe(text_model, prompt)

                            if response_text:
                                suggested_category = response_text.strip()
                                if suggested_category in base_categories:
                                    st.session_state.trans_category = suggested_category
                                    st.rerun()
                                else:
                                    st.warning(f"AI suggested '{suggested_category}', which isn't in your list.")
                            else:
                                raise Exception("Empty response from model")
                        except Exception as e:
                            st.error(f"Could not reach AI. Details: {e}")
                else:
                    st.warning("Please type a description first!")

            category = st.selectbox("What? (Category)", base_categories, key="trans_category")

        st.write("---")
        submit_btn_col1, submit_btn_col2 = st.columns([1, 1])
        
        with submit_btn_col1:
            button_text = "💾 Save Changes" if is_editing else "Create Transaction"
            if st.button(button_text, type="primary", use_container_width=True):
                if not description or amount <= 0:
                    st.error("Please enter a valid description and amount.")
                else:
                    try:
                        current_time = datetime.datetime.now().time()
                        final_datetime = datetime.datetime.combine(date, current_time)

                        transaction_data = {
                            "user_id": st.session_state.user_id,
                            "account_id": account_dict[account_name],
                            "amount": to_inr(amount),  # Convert to INR for storage
                            "type": st.session_state.trans_type,
                            "category": category,
                            "description": encrypt_data(description),
                            "transaction_time": str(final_datetime),
                            "is_recurring": is_recurring
                        }

                        # Amount for balance calculation (already converted to INR)
                        new_amount = to_inr(amount)
                        
                        if is_editing:
                            trans_id_to_update = editing_data['id']
                            supabase.table("transactions").update(transaction_data).eq("id", trans_id_to_update).execute()
                            
                            old_amount = float(editing_data['amount'])
                            old_type = editing_data['type']
                            old_acc_id = editing_data['account_id']
                            new_acc_id = account_dict[account_name]
                            new_type = st.session_state.trans_type

                            old_bal_mod = old_amount if old_type == "Income" else -old_amount
                            old_bal_res = supabase.table("accounts").select("balance").eq("id", old_acc_id).execute()
                            corrected_old_bal = float(old_bal_res.data[0]['balance']) - old_bal_mod
                            supabase.table("accounts").update({"balance": corrected_old_bal}).eq("id", old_acc_id).execute()
                            
                            new_bal_mod = new_amount if new_type == "Income" else -new_amount
                            current_bal_res = supabase.table("accounts").select("balance").eq("id", new_acc_id).execute()
                            new_bal = float(current_bal_res.data[0]['balance']) + new_bal_mod
                            supabase.table("accounts").update({"balance": new_bal}).eq("id", new_acc_id).execute()

                            st.success(f"Successfully updated '{description}' logged on {date}!")
                            
                            keys_to_clear = ['editing_transaction_data','trans_amount', 'trans_desc', 'trans_date', 'trans_category', 'trans_type', 'trans_account_name', 'trans_recurring']
                            for key in keys_to_clear:
                                if key in st.session_state:
                                    del st.session_state[key]
                                    
                            # Drop the overlay and return to the parent screen
                            st.session_state.force_page = None
                            st.rerun() 
                            
                        else:
                            # Insert New Transaction (capture its id so the anomaly
                            # check can measure against PAST transactions only)
                            ins_res = supabase.table("transactions").insert(transaction_data).execute()
                            new_ids = [r["id"] for r in (ins_res.data or []) if r.get("id")]
                            
                            balance_modifier = new_amount if st.session_state.trans_type == "Income" else -new_amount
                            current_bal_res = supabase.table("accounts").select("balance").eq("id", account_dict[account_name]).execute()
                            new_bal = float(current_bal_res.data[0]['balance']) + balance_modifier
                            supabase.table("accounts").update({"balance": new_bal}).eq("id", account_dict[account_name]).execute()

                            # ✨ NEW: Trigger Anomaly Engine instantly for Expenses!
                            if st.session_state.trans_type == "Expense":
                                user_res = supabase.table("profiles").select("email, full_name").eq("id", st.session_state.user_id).execute()
                                if user_res.data:
                                    user_email = user_res.data[0].get("email")
                                    raw_name = user_res.data[0].get("full_name")
                                    user_name = raw_name.split(" ")[0] if raw_name else "User"
                                    
                                    check_and_alert_anomaly(
                                        supabase=supabase,
                                        user_id=st.session_state.user_id,
                                        user_email=user_email,
                                        user_name=user_name,
                                        amount=new_amount,
                                        category=category,
                                        description=description,
                                        transaction_time_iso=str(final_datetime),
                                        account_name=account_name,
                                        exclude_ids=new_ids
                                    )

                            st.success(f"Successfully logged {st.session_state.trans_type} of {fmt_money(amount, dp=2)}!")
                            
                            keys_to_clear = ['trans_amount', 'trans_desc', 'trans_date', 'trans_category', 'trans_type', 'trans_recurring']
                            for key in keys_to_clear:
                                if key in st.session_state:
                                    del st.session_state[key]
                                    
                            # Drop the overlay and return to the parent screen
                            st.session_state.force_page = None
                            st.rerun() 
                            
                    except Exception as e:
                        st.error(f"Failed to save transaction: {e}")