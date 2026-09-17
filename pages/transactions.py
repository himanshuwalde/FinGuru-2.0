import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from utils.security import encrypt_data, decrypt_data
from utils.currency import fmt_label, fmt_money
from utils.ai_client import get_gemini_client, get_best_model, generate_content_safe
import time

import services.document_processing as dp

# Initialize AI client
genai_client = get_gemini_client()

@st.dialog("Delete transactions")
def confirm_bulk_delete(supabase):
    """Ask before permanently deleting the selected transactions."""
    count = len(st.session_state.selected_txns)
    st.warning(f"⚠️ Are you sure you want to permanently delete **{count}** "
               "selected transactions? This cannot be undone.")
    c1, c2 = st.columns(2)
    if c1.button("🗑️ Yes, delete", type="primary", use_container_width=True):
        with st.spinner("Deleting records..."):
            try:
                ids_to_delete = list(st.session_state.selected_txns)
                supabase.table("transactions").delete().in_("id", ids_to_delete).execute()
                st.session_state.selected_txns.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Failed to delete transactions: {e}")
                return  # keep the dialog open so the error is visible
    if c2.button("Cancel", use_container_width=True):
        st.rerun()


def render_page(supabase):
    
    # --- MEMORY INITIALIZATION ---
    if 'trans_search_query' not in st.session_state: st.session_state.trans_search_query = ""
    if 'trans_current_page' not in st.session_state: st.session_state.trans_current_page = 1
    if 'jump_page_input' not in st.session_state: st.session_state.jump_page_input = 1 # 👈 Add this
    if 'editing_transaction_data' in st.session_state: del st.session_state.editing_transaction_data
    if 'show_scanner' not in st.session_state: st.session_state.show_scanner = False
    
    # ✨ ADDED: Bulk Delete State Trackers
    if 'selected_txns' not in st.session_state: st.session_state.selected_txns = set()

    # --- Defined Callbacks Function ---
    def go_to_scanner():
        st.session_state.force_page = "add_transaction"

    # ✨ ADDED: Checkbox toggle logic
    def toggle_selection(txn_id):
        if txn_id in st.session_state.selected_txns:
            st.session_state.selected_txns.remove(txn_id)
        else:
            st.session_state.selected_txns.add(txn_id)

    # --- FETCH ACCOUNTS AND TRANSACTIONS ---
    try:
        acc_response = supabase.table("accounts").select("*").eq("user_id", st.session_state.user_id).order("created_at").execute()
        user_accounts = acc_response.data
        
        primary_acc = next((acc for acc in user_accounts if acc.get('is_primary')), None)
        if not primary_acc:
            if len(user_accounts) > 0:
                primary_acc = user_accounts[0]
            else:
                st.warning("📊 You need to add a Bank Account in the Dashboard before viewing transactions!")
                return
        
        account_name = f"{primary_acc['account_name']} Savings Account"
        account_id = primary_acc['id']
        
        trans_res = supabase.table("transactions").select("*").eq("user_id", st.session_state.user_id).execute()
        all_transactions = trans_res.data
        
        account_transactions = [t for t in all_transactions if t['account_id'] == account_id]
        
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        return

    # --- THE HEADER WITH BUTTONS ---
    header_col1, header_col2, header_col3 = st.columns([3, 1.4, 1.4]) 
    
    with header_col1:
        # ✨ THE FIX: Moved gradient styles to a dedicated CSS class with !important tags to prevent Streamlit render glitches
        st.markdown(f"""
            <div class="page-header">
            <h2>{account_name}</h2>
            <p>List of all your transactions for {account_name}.</p>
        </div>
        """, unsafe_allow_html=True)
        
    with header_col2:
        st.write("") 
        st.write("") 
        if st.button("📸 AI Document Scanner", use_container_width=True):
            st.session_state.show_scanner = not st.session_state.show_scanner
            st.rerun()

    with header_col3:
        st.write("") 
        st.write("") 
        st.button("➕ Add Transaction", type="primary", use_container_width=True, on_click=go_to_scanner, key="trans_page_add_btn")

    # ==========================================
    # ✨ SECTION: AI DOCUMENT SCANNER UI
    # ==========================================
    if st.session_state.show_scanner:
        with st.container(border=True):
            st.subheader("📸 AI Statement & Receipt Scanner")
            st.markdown("Upload a Bank Statement (PDF) or Receipt (Image). Our AI will extract the transactions and add them to your ledger.")
            
            uploaded_file = st.file_uploader("Upload Document", type=['pdf', 'png', 'jpg', 'jpeg'])
            
            if uploaded_file and st.button("Extract & Sync Transactions", type="primary"):
                with st.spinner("🧠 AI is analyzing the document... Please wait."):
                    try:
                        target_model = get_best_model(genai_client, prefer_flash=True)
                        model = genai_client.GenerativeModel(target_model)
                        st.info(f"*(Diagnostic: Successfully connected to next-gen model '{target_model}')*)")

                        # #2 — Pre-check (type + size)
                        pre_err = dp.validate_upload(uploaded_file.name, uploaded_file.size)
                        if pre_err:
                            st.error(f"⚠️ **Pre-check failed:** {pre_err}")
                        else:
                            # #3 — AI extraction via shared service
                            extracted = dp.extract_with_gemini(
                                genai_client, model,
                                uploaded_file.getvalue(),
                                mime_type=uploaded_file.type,
                                filename=uploaded_file.name,
                            )
                            if extracted["error"]:
                                err = extracted["error"]
                                st.error(f"⚠️ **Scanner Error:** {err}")
                                if "400" in err and "pages" in err.lower():
                                    st.warning("🔒 **Document Locked!** This PDF is encrypted with a password. Please open it on your computer, hit 'Print', save it as an unlocked PDF, and upload that copy.")
                            else:
                                # #4 — Schema validation + reconciliation
                                clean_txns, warnings = dp.validate_transactions(extracted["transactions"])
                                for w in warnings:
                                    st.warning(w)
                                rec = dp.reconcile(clean_txns, extracted["opening_balance"], extracted["closing_balance"])
                                if rec["status"] == "mismatch":
                                    st.warning(f"⚖️ {rec['message']}")

                                # Fetch user profile for anomaly alerts
                                user_email, user_name = None, "User"
                                try:
                                    user_res = supabase.table("profiles").select("email, full_name").eq("id", st.session_state.user_id).execute()
                                    if user_res.data:
                                        user_email = user_res.data[0].get("email")
                                        raw_name = user_res.data[0].get("full_name")
                                        user_name = raw_name.split(" ")[0] if raw_name else "User"
                                except Exception:
                                    pass

                                # #5 — Dedup + persist + anomaly alerts
                                if not clean_txns:
                                    st.warning("Could not find any clear transactions in this document.")
                                else:
                                    res = dp.persist_with_dedup(
                                        supabase,
                                        st.session_state.user_id,
                                        user_email,
                                        user_name,
                                        account_id,
                                        primary_acc['account_name'],
                                        clean_txns,
                                    )
                                    if res["error"]:
                                        st.error(f"⚠️ **Sync Error:** {res['error']}")
                                    else:
                                        st.session_state.show_scanner = False
                                        label = f"✅ Successfully extracted and synced {res['inserted']} transactions using {target_model}!"
                                        if res["duplicates"]:
                                            label += f" ({res['duplicates']} duplicates skipped)"
                                        st.success(label)
                                        time.sleep(1.5)
                                        st.rerun()
                    except Exception as e:
                        error_msg = str(e)
                        st.error(f"⚠️ **Scanner Error:** {error_msg}")
                        if "400" in error_msg and "pages" in error_msg.lower():
                            st.warning("🔒 **Document Locked!** This PDF is encrypted with a password. Please open it on your computer, hit 'Print', save it as an unlocked PDF, and upload that copy.")
        st.write("---")

    # --- SECTION: OVERVIEW AND CHART ---
    if len(account_transactions) > 0:
        df = pd.DataFrame(account_transactions)
        df['amount'] = pd.to_numeric(df['amount'])
        
        df['description'] = df['description'].apply(lambda x: decrypt_data(str(x)) if pd.notnull(x) else "")
        df['transaction_time'] = pd.to_datetime(df['transaction_time'], format='ISO8601', utc=True).dt.tz_localize(None)
        df['month_period'] = df['transaction_time'].dt.to_period('M').dt.start_time

        st.write("")
        with st.container(border=True):
            header_col, filter_col = st.columns([4, 1.2])
            with header_col:
                st.subheader("Transaction Overview")
            with filter_col:
                time_granularity = st.selectbox(
                    "View By Timeframe", 
                    ["This Month", "Last Month", "This Quarter", "This 6 Months", "This Year", "All Time"],
                    index=2, 
                    label_visibility="collapsed"
                )

            today = datetime.now()
            start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            if time_granularity == "This Month":
                start_date = start_of_month
            elif time_granularity == "Last Month":
                start_date = (start_of_month - timedelta(days=1)).replace(day=1)
            elif time_granularity == "This Quarter":
                quarter_month = 3 * ((today.month - 1) // 3) + 1
                start_date = today.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            elif time_granularity == "This 6 Months":
                six_months_ago_month = today.month - 5
                six_months_ago_year = today.year
                if six_months_ago_month <= 0:
                    six_months_ago_month += 12
                    six_months_ago_year -= 1
                start_date = today.replace(year=six_months_ago_year, month=six_months_ago_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            elif time_granularity == "This Year":
                start_date = today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else: 
                start_date = datetime(2000, 1, 1)

            filtered_df = df[(df['transaction_time'] >= start_date)]
            
            total_income = filtered_df[filtered_df['type'] == 'Income']['amount'].sum() if not filtered_df.empty else 0
            total_expense = filtered_df[filtered_df['type'] == 'Expense']['amount'].sum() if not filtered_df.empty else 0
            net_savings = total_income - total_expense

            st.write("")
            col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
            col_kpi1.metric("💰 Total Income", fmt_money(total_income, dp=2))
            col_kpi2.metric("💸 Total Expenses", fmt_money(total_expense, dp=2))
            col_kpi3.metric("🏦 Net", fmt_money(net_savings, dp=2))
            st.write("") 
            
            if not filtered_df.empty:
                trend_df = filtered_df.groupby(['month_period', 'type'])['amount'].sum().reset_index()
                trend_df = trend_df.sort_values('month_period')
                trend_df['month_str'] = trend_df['month_period'].dt.strftime('%b %Y')
                
                fig_bar = px.bar(trend_df, x='month_str', y='amount', color='type', 
                                 barmode='group', 
                                 color_discrete_map={'Income': '#2ecc71', 'Expense': '#e74c3c'})
                
                fig_bar.update_layout(
                    margin=dict(t=10, b=10, l=10, r=10), 
                    xaxis_title="", 
                    yaxis_title=fmt_label("Amount (₹)"),
                    height=350,
                    xaxis={'categoryorder': 'array', 'categoryarray': trend_df['month_str'].unique()},
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)"
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info(f"📊 No transactions found for '{time_granularity}'.")

        st.write("---")

        # ==========================================
        #   SECTION: TRANSACTIONS LIST
        # ==========================================
        st.subheader("Your Transactions List")
        
        with st.container(border=True):
            f_col1, f_col2, f_col3 = st.columns([2.5, 1, 1])
            with f_col1:
                search_query = st.text_input("Search", value=st.session_state.trans_search_query, placeholder="🔍 Search transactions...", label_visibility="collapsed")
                st.session_state.trans_search_query = search_query
            with f_col2:
                filter_type = st.selectbox("Type", ["All Types", "Expense", "Income"], label_visibility="collapsed")
            with f_col3:
                base_categories = ["Food & Dining", "Transport", "Shopping", "Entertainment", "Groceries", "Utilities", "Income", "Education", "Other"]
                filter_category = st.selectbox("Category", ["All Categories"] + base_categories, label_visibility="collapsed")
            
            st.write("---")

            # ✨ ADDED: Dynamic Bulk Delete Button Panel
            if len(st.session_state.selected_txns) > 0:
                del_col, _ = st.columns([1.5, 4])
                with del_col:
                    if st.button(f"🗑️ Delete Selected ({len(st.session_state.selected_txns)})", type="primary", use_container_width=True):
                        confirm_bulk_delete(supabase)
                st.write("") # Padding
            
            list_df = df.copy()
            if search_query:
                list_df = list_df[
                    list_df['description'].str.contains(search_query, case=False, na=False) |
                    list_df['category'].str.contains(search_query, case=False, na=False) |
                    list_df['amount'].astype(str).str.contains(search_query)
                ]
            if filter_type != "All Types":
                list_df = list_df[list_df['type'] == filter_type]
            if filter_category != "All Categories":
                list_df = list_df[list_df['category'] == filter_category]

            if not list_df.empty:
                st.markdown("<div style='display: flex; gap: 0px; margin-bottom: 5px;'>", unsafe_allow_html=True)
                
                t1, t2, t3, t4, t5, t6, t7 = st.columns([0.6, 1.2, 3, 2, 2, 1, 0.8])
                t1.markdown(f"""<div style='color: var(--text-color); opacity: 0.8; font-size: 0.85rem; font-weight: 500;'>Select</div>""", unsafe_allow_html=True) 
                t2.markdown(f"""<div style='color: var(--text-color); opacity: 0.8; font-size: 0.85rem; font-weight: 500;'>Date ↓</div>""", unsafe_allow_html=True)
                t3.markdown(f"""<div style='color: var(--text-color); opacity: 0.8; font-size: 0.85rem; font-weight: 500;'>Description</div>""", unsafe_allow_html=True)
                t4.markdown(f"""<div style='color: var(--text-color); opacity: 0.8; font-size: 0.85rem; font-weight: 500;'>Category</div>""", unsafe_allow_html=True)
                t5.markdown(f"""<div style='color: var(--text-color); opacity: 0.8; font-size: 0.85rem; font-weight: 500;'>Amount</div>""", unsafe_allow_html=True)
                t6.markdown(f"""<div style='color: var(--text-color); opacity: 0.8; font-size: 0.85rem; font-weight: 500;'>Recurring</div>""", unsafe_allow_html=True)
                t7.markdown(f"""<div style='color: var(--text-color); opacity: 0.8; font-size: 0.85rem; font-weight: 500;'>Edit</div>""", unsafe_allow_html=True) 
                st.markdown("</div>", unsafe_allow_html=True)
                
                list_df = list_df.sort_values(by="transaction_time", ascending=False)
                
                ITEMS_PER_PAGE = 10 
                total_transactions = len(list_df)
                total_pages = max((total_transactions + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE, 1)

                if st.session_state.trans_current_page > total_pages:
                    st.session_state.trans_current_page = 1
                
                curr_page = st.session_state.trans_current_page
                start_row = (curr_page - 1) * ITEMS_PER_PAGE
                end_row = start_row + ITEMS_PER_PAGE
                paginated_df = list_df.iloc[start_row:end_row]

                def initiate_edit(target_data):
                    st.session_state.editing_transaction_data = target_data 
                    st.session_state.force_page = "add_transaction"
                
                for _, row in paginated_df.iterrows():
                    trans_id = row['id']
                    date_str = row['transaction_time'].strftime("%b %d, %Y")
                    desc = str(row['description']).title()
                    
                    if row['type'] == 'Income':
                        amt_color = "#2ecc71" 
                        amount_display = f"+{fmt_money(row['amount'], dp=2)}"
                    else:
                        amt_color = "#e74c3c" 
                        amount_display = f"-{fmt_money(row['amount'], dp=2)}"
                        
                    category_styles = {
                        "Food & Dining": "background: var(--secondary-background-color); color: #db2777; border: 1px solid rgba(219,39,119,0.3); border-radius: 6px; padding: 4px 8px; font-size: 0.8rem;",
                        "Transport": "background: var(--secondary-background-color); color: #0284c7; border: 1px solid rgba(2,132,199,0.3); border-radius: 6px; padding: 4px 8px; font-size: 0.8rem;",
                        "Shopping": "background: var(--secondary-background-color); color: #4f46e5; border: 1px solid rgba(79,70,229,0.3); border-radius: 6px; padding: 4px 8px; font-size: 0.8rem;",
                        "Groceries": "background: var(--secondary-background-color); color: #16a34a; border: 1px solid rgba(22,163,74,0.3); border-radius: 6px; padding: 4px 8px; font-size: 0.8rem;",
                        "Utilities": "background: var(--secondary-background-color); color: #b45309; border: 1px solid rgba(180,83,9,0.3); border-radius: 6px; padding: 4px 8px; font-size: 0.8rem;",
                        "Entertainment": "background: var(--secondary-background-color); color: #c53030; border: 1px solid rgba(197,48,48,0.3); border-radius: 6px; padding: 4px 8px; font-size: 0.8rem;",
                        "Education": "background: var(--secondary-background-color); color: var(--text-color); border: 1px solid rgba(150,150,150,0.4); border-radius: 6px; padding: 4px 8px; font-size: 0.8rem;",
                        "Other": "background: var(--secondary-background-color); color: var(--text-color); border: 1px solid rgba(150,150,150,0.4); border-radius: 6px; padding: 4px 8px; font-size: 0.8rem;",
                        "Income": "background: var(--secondary-background-color); color: #16a34a; border: 1px solid rgba(22,163,74,0.3); border-radius: 6px; padding: 4px 8px; font-size: 0.8rem;"
                    }
                    cat_style = category_styles.get(row['category'], category_styles['Other'])

                    t1, t2, t3, t4, t5, t6, t7 = st.columns([0.6, 1.2, 3, 2, 2, 1, 0.8])
                    
                    is_selected = trans_id in st.session_state.selected_txns
                    t1.checkbox("", value=is_selected, key=f"chk_{trans_id}", on_change=toggle_selection, args=(trans_id,), label_visibility="collapsed")
                    
                    t2.markdown(f"<div style='font-size: 0.9rem; color: var(--text-color); opacity: 0.7; padding-top: 0.4rem;'>{date_str}</div>", unsafe_allow_html=True)
                    t3.markdown(f"<div style='font-weight: 500; font-size: 0.95rem; color: var(--text-color); padding-top: 0.4rem;'>{desc}</div>", unsafe_allow_html=True)
                    t4.markdown(f"<div style='padding-top: 0.4rem;'><span style='{cat_style}'>{row['category']}</span></div>", unsafe_allow_html=True)
                    t5.markdown(f"<div style='font-weight: bold; color: {amt_color}; font-size: 1rem; padding-top: 0.4rem;'>{amount_display}</div>", unsafe_allow_html=True)
                    
                    recurring_icon = "🔁" if row.get('is_recurring') else "🕒"
                    recurring_help = "Monthly Recurring" if row.get('is_recurring') else "One-time"
                    t6.markdown(f"<div style='text-align: center; font-size: 1rem; padding-top: 0.4rem;' title='{recurring_help}'>{recurring_icon}</div>", unsafe_allow_html=True)
                    
                    t7.button("✏️", key=f"edit_btn_{trans_id}", help=f"Edit '{desc}'", on_click=initiate_edit, args=(row,), use_container_width=True)
                    
                    st.markdown("<hr style='margin: 0.2rem 0; border: none; border-bottom: 1px solid rgba(150,150,150,0.2);' />", unsafe_allow_html=True)
                
                st.write("")
                page_cols = st.columns([1, 1, 1.5, 1, 1])

                # ✅ FIX: All three callbacks now sync both trans_current_page AND jump_page_input
                # so the number_input always reflects the true current page.
                def prev_page():
                    st.session_state.trans_current_page -= 1
                    st.session_state.jump_page_input = st.session_state.trans_current_page

                def next_page():
                    st.session_state.trans_current_page += 1
                    st.session_state.jump_page_input = st.session_state.trans_current_page

                def jump_page():
                    st.session_state.trans_current_page = st.session_state.jump_page_input

                if curr_page > 1:
                    page_cols[1].button("← Previous", key="trans_prev_btn", on_click=prev_page, use_container_width=True)

                with page_cols[2]:
                    st.number_input(
                        "Jump to page", 
                        min_value=1, 
                        max_value=total_pages, 
                        # value=curr_page,   # ✅ Always seeds from the true current page
                        step=1, 
                        key="jump_page_input", 
                        on_change=jump_page,
                        label_visibility="collapsed",
                        help=f"Type a number and press Enter to jump to a page (1 to {total_pages})"
                    )
                    st.markdown(f"<div style='text-align: center; color: var(--text-color); opacity: 0.8; font-size: 0.85rem; padding-top: 0.2rem; font-weight: 500;'>Page {curr_page} of {total_pages}</div>", unsafe_allow_html=True)

                if curr_page < total_pages:
                    page_cols[3].button("Next →", key="trans_next_btn", on_click=next_page, use_container_width=True)
                
                st.caption(f"<div style='text-align: center; color: var(--text-color); opacity: 0.6;'>Displaying {start_row + 1}-{min(end_row, total_transactions)} of {total_transactions} transactions.</div>", unsafe_allow_html=True)
            
            else:
                st.info("No transactions found matching your search and filters.")

    else:
        st.info("📊 No transactions found! Go to Dashboard or '➕ Add Transaction' button to log some data.")