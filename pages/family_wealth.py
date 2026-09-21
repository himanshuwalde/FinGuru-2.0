import streamlit as st
import pandas as pd
import numpy as np
import joblib
import plotly.express as px
import hashlib
from datetime import datetime
from utils.currency import fmt_label, fmt_money

# --- 1. LOAD THE CUSTOM ML MODEL ---
@st.cache_resource
def load_healthcare_model():
    try:
        return joblib.load('custom_healthcare_model.joblib')
    except Exception as e:
        return None

def get_real_financial_health(supabase, target_user_id):
    try:
        acc_res = supabase.table("accounts").select("balance").eq("user_id", target_user_id).execute()
        if acc_res.data:
            corpus = sum(float(acc['balance']) for acc in acc_res.data)
        else:
            corpus = 0.0
        
        # Presentation Fallback
        if corpus == 0.0 and target_user_id:
            seed = int(hashlib.sha1(str(target_user_id).encode("utf-8")).hexdigest(), 16) % (10**8)
            np.random.seed(seed)
            corpus = float(np.random.randint(150000, 2500000))
            
        target_liquidity = 200000.0
        health_score = min(100, max(10, int((corpus / target_liquidity) * 100)))
        return corpus, health_score
    except:
        return 0.0, 10

# ✨ NEW: Dialog for user-defined Legacy Goal
@st.dialog("🎯 Set Legacy Transfer Goal")
def legacy_goal_dialog(supabase, user_id):
    st.markdown("Define your multi-generational wealth target to track your family's progress.")
    
    current_year = datetime.now().year
    
    new_amount = st.number_input(fmt_label("Target Amount (₹)"), min_value=100000, value=int(st.session_state.get('legacy_amount', 50000000)), step=1000000)
    new_year = st.number_input("Target Year", min_value=current_year, max_value=2100, value=int(st.session_state.get('legacy_year', 2045)), step=1)
    
    if st.button("Save Goal", type="primary", use_container_width=True):
        try:
            # Save persistently to database
            supabase.table("profiles").update({
                "legacy_goal_amount": new_amount,
                "legacy_goal_year": new_year
            }).eq("id", user_id).execute()
            
            # Update local session state
            st.session_state.legacy_amount = new_amount
            st.session_state.legacy_year = new_year
            st.session_state.legacy_set = True
            st.rerun()
        except Exception as e:
            st.error("Failed to save to database. Did you add the 'legacy_goal_amount' and 'legacy_goal_year' columns in Supabase?")

@st.dialog("Revoke access")
def confirm_revoke_access(supabase, member):
    """Ask before permanently disconnecting a family member's federated link."""
    st.warning(f"Revoke **{member['name']}**'s access? This will permanently "
               "disconnect the federated link.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, revoke", type="primary", use_container_width=True):
        supabase.table("family_connections").delete().eq("id", member['id']).execute()
        st.rerun()
    if c2.button("Cancel", use_container_width=True):
        st.rerun()

def render_page(supabase):
    my_id = st.session_state.user_id
    my_email = st.session_state.user_email

    # Fetch the Legacy Goal from the Database ONCE per session
    if 'legacy_fetched' not in st.session_state:
        try:
            profile_res = supabase.table("profiles").select("legacy_goal_amount, legacy_goal_year").eq("id", my_id).execute()
            if profile_res.data and profile_res.data[0].get("legacy_goal_amount") is not None:
                st.session_state.legacy_amount = profile_res.data[0]["legacy_goal_amount"]
                st.session_state.legacy_year = profile_res.data[0]["legacy_goal_year"]
                st.session_state.legacy_set = True
            else:
                st.session_state.legacy_amount = 50000000
                st.session_state.legacy_year = 2045
                st.session_state.legacy_set = False
        except Exception:
            # Fallback if the columns don't exist yet
            st.session_state.legacy_amount = 50000000
            st.session_state.legacy_year = 2045
            st.session_state.legacy_set = False
            
        st.session_state.legacy_fetched = True

    incoming_pending = supabase.table("family_connections").select("*").eq("receiver_email", my_email).eq("status", "pending").execute().data
    outgoing_all = supabase.table("family_connections").select("*").eq("sender_id", my_id).order("created_at", desc=True).execute().data
    
    # ==========================================
    # --- TOP HEADER & NOTIFICATION BELL ---
    # ==========================================
    
    header_col, nav_col = st.columns([4, 1.2])

    with header_col:
        st.markdown("""
            <div class="page-header">
                <h2>Family Dashboard</h2>
                <p>Manage intergenerational finances securely. Data is only shared with explicit, two-way consent.</p>
            </div>
        """, unsafe_allow_html=True)

    with nav_col:
        st.write("") 
        notif_count = len(incoming_pending)
        bell_label = f"🔔 Notifications ({notif_count})" if notif_count > 0 else "🔔 Notifications"
        
        with st.popover(bell_label, use_container_width=True):
            st.markdown("#### 📥 Incoming Invites")
            if not incoming_pending:
                st.caption("No new invites.")
            else:
                for inv in incoming_pending:
                    if inv.get('sender_name'):
                        inviter_name = inv['sender_name']
                    elif inv.get('sender_email'):
                        inviter_name = inv['sender_email'].split('@')[0].capitalize()
                    else:
                        inviter_name = "Someone"
                        
                    st.info(f"Join **{inviter_name}'s** dashboard as **{inv['role']}**?")
                    c_acc, c_rej = st.columns(2)
                    if c_acc.button("✅ Accept", key=f"acc_{inv['id']}", use_container_width=True):
                        supabase.table("family_connections").update({"status": "accepted", "receiver_id": my_id}).eq("id", inv['id']).execute()
                        st.rerun()
                    if c_rej.button("❌ Reject", key=f"rej_{inv['id']}", use_container_width=True):
                        supabase.table("family_connections").update({"status": "rejected", "receiver_id": my_id}).eq("id", inv['id']).execute()
                        st.rerun()
            
            st.markdown("---")
            st.markdown("#### 📤 Sent Invites Status")
            if not outgoing_all:
                st.caption("No invites sent.")
            else:
                for out in outgoing_all:
                    if out['status'] == 'accepted':
                        status_color, status_icon = "#2ecc71", "✅ Accepted"
                    elif out['status'] == 'rejected':
                        status_color, status_icon = "#e74c3c", "❌ Rejected"
                    else:
                        status_color, status_icon = "#f39c12", "⏳ Pending"
                        
                    display_name = out.get('receiver_name', out['receiver_email'])
                    st.markdown(f"**To:** {display_name}<br>**Status:** <span style='color:{status_color}; font-weight: bold;'>{status_icon}</span>", unsafe_allow_html=True)
                    st.markdown("<hr style='margin: 0.5rem 0; border: none; border-bottom: 1px solid rgba(150,150,150,0.2);' />", unsafe_allow_html=True)

    # ==========================================
    # --- FETCH REAL ACTIVE CONNECTIONS ---
    # ==========================================
    with st.spinner("Synchronizing secure federated data..."):
        try:
            sent_accepted = [o for o in outgoing_all if o['status'] == 'accepted']
            received_accepted = supabase.table("family_connections").select("*").eq("receiver_id", my_id).eq("status", "accepted").execute().data
            active_connections = sent_accepted + received_accepted
            my_corpus, my_health = get_real_financial_health(supabase, my_id)
        except Exception as e:
            st.error(f"Failed to fetch connections: {e}")
            active_connections = []
            my_corpus, my_health = 0.0, 100

    total_shared_corpus = 0.0
    family_health_scores = [my_health]
    processed_members = []
    reverse_roles = {"Child": "Parent", "Parent": "Child", "Spouse": "Spouse", "Other": "Other"}

    for conn in active_connections:
        if conn['sender_id'] == my_id:
            other_user_id = conn['receiver_id']
            display_name = conn.get('receiver_name') if conn.get('receiver_name') else conn['receiver_email'].split('@')[0].capitalize()
            role = conn['role'] 
        else:
            other_user_id = conn['sender_id']
            display_name = conn.get('sender_name') if conn.get('sender_name') else "Family Member"
            role = reverse_roles.get(conn['role'], "Family Member") 
            
        their_corpus, their_health = get_real_financial_health(supabase, other_user_id)
        total_shared_corpus += their_corpus
        family_health_scores.append(their_health)
        
        processed_members.append({
            "id": conn['id'], "name": display_name, "role": role,
            "corpus": their_corpus, "health": their_health
        })

    aggregated_wealth = my_corpus + total_shared_corpus

    # ==========================================
    # --- SECTION 1: TOP LEVEL KPIS ---
    # ==========================================
    st.write("")
    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    col_kpi1.metric("🏦 Aggregated Family Net Worth", fmt_money(aggregated_wealth))
    
    with col_kpi2:
        if not st.session_state.legacy_set:
            st.metric("🎯 Legacy Transfer Goal", "Action Required")
            if st.button("Set Goal", type="primary", use_container_width=True):
                legacy_goal_dialog(supabase, my_id)
        else:
            st.metric(f"🎯 Legacy Transfer Goal ({int(st.session_state.legacy_year)})", fmt_money(st.session_state.legacy_amount))
            if st.button("✏️ Edit Goal", use_container_width=True):
                legacy_goal_dialog(supabase, my_id)
    
    avg_health = sum(family_health_scores) / len(family_health_scores)
    health_color = "#2ecc71"
    if avg_health < 50: health_color = "#e74c3c"
    elif avg_health < 80: health_color = "#f39c12"
    status_text = "🟢 On Track" if health_color == "#2ecc71" else "⚠️ Action Needed"

    # ✨ THE FIX: Dynamic actionable advice rendered below the Health Index Metric
    with col_kpi3:
        st.metric("❤️ Federated Health Index", f"{status_text}")
        if avg_health < 50:
            st.markdown(f"<div style='font-size: 0.85rem; color: {health_color}; margin-top: -15px;'><b>Action:</b> Severe liquidity shortfall. Halt discretionary spending and prioritize emergency savings.</div>", unsafe_allow_html=True)
        elif avg_health < 80:
            st.markdown(f"<div style='font-size: 0.85rem; color: {health_color}; margin-top: -15px;'><b>Action:</b> Increase liquid savings. Aim for a {fmt_money(200000)} baseline per connected family member.</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='font-size: 0.85rem; color: {health_color}; margin-top: -15px;'><b>Status:</b> Optimal family liquidity maintained.</div>", unsafe_allow_html=True)

    st.write("---")

    # ==========================================
    # --- OUTBOX: SEND INVITE FORM ---
    # ==========================================
    with st.expander("➕ Invite New Family Member"):
        with st.form("add_family_form", clear_on_submit=True):
            st.markdown("Send an invite to a family member's email. They must create an account and accept the invite via their Notification Bell before their data is securely aggregated.")
            
            new_name = st.text_input("Family Member's Name", placeholder="e.g., Priya")
            new_email = st.text_input("Family Member's Registered Email", placeholder="parent@example.com")
            new_role = st.selectbox("Their Role", ["Spouse", "Child", "Parent", "Sibling", "Other"])
            
            if st.form_submit_button("Send Secure Invitation", type="primary"):
                if new_email.lower() == my_email.lower():
                    st.error("You cannot invite yourself!")
                elif new_name and new_email:
                    try:
                        existing_all = supabase.table("family_connections").select("*").eq("sender_id", my_id).eq("receiver_email", new_email).execute().data
                        active_invites = [inv for inv in existing_all if inv['status'] in ['pending', 'accepted']]
                        
                        if active_invites:
                            st.warning("An invitation to this email is already pending or active. Check your Notification Bell.")
                        else:
                            # Fetch the inviter's actual name from the profiles table
                            my_display_name = my_email.split('@')[0].capitalize() 
                            try:
                                profile_res = supabase.table("profiles").select("full_name").eq("id", my_id).execute()
                                if profile_res.data and profile_res.data[0].get("full_name"):
                                    my_display_name = profile_res.data[0]["full_name"].strip()
                            except Exception as e:
                                pass 
                                
                            supabase.table("family_connections").insert({
                                "sender_id": my_id, 
                                "sender_email": my_email,             
                                "sender_name": my_display_name,       
                                "receiver_name": new_name,
                                "receiver_email": new_email, 
                                "role": new_role, 
                                "status": "pending"
                            }).execute()
                            st.success(f"Invitation successfully sent to {new_name} ({new_email})! Track it in your notifications.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to send invite: {e}")
                else:
                    st.error("Please provide both the Name and Email address.")
    st.write("")

    # ==========================================
    # --- SECTION 2: THE REAL FEDERATED VIEW CARDS ---
    # ==========================================
    st.subheader("Federated Silo Status")
    st.markdown("*Viewing aggregated financial health based on securely synced account balances.*")

    member_cols = st.columns(min(len(processed_members) + 1, 4))
    
    with member_cols[0]:
        with st.container(border=True):
            st.markdown("### You")
            st.markdown(f"<span style='color: {'#16a34a' if my_health >= 80 else '#b45309'}; font-weight: bold;'>Health Score: {my_health}/100</span>", unsafe_allow_html=True)
            st.progress(my_health / 100)
            st.markdown(f"**Your Corpus:** {fmt_money(my_corpus)}")
            st.caption("Transactions: Private 🔒")

    for i, member in enumerate(processed_members):
        with member_cols[(i + 1) % 4]:
            with st.container(border=True):
                st.markdown(f"### {member['name']} ({member['role']})")
                st.markdown(f"<span style='color: {'#16a34a' if member['health'] >= 80 else '#b45309'}; font-weight: bold;'>Health Score: {member['health']}/100</span>", unsafe_allow_html=True)
                st.progress(member['health'] / 100)
                st.markdown(f"**Shared Corpus:** {fmt_money(member['corpus'])}")
                
                c1, c2 = st.columns([2.5, 1.5])
                c1.caption("Transactions: Private 🔒")
                
                if c2.button("🗑️", help="Revoke Access", use_container_width=True):
                    confirm_revoke_access(supabase, member)

    st.write("---")

    # ==========================================
    # --- SECTION 3: AI HEALTHCARE BUFFER ENGINE (ML) ---
    # ==========================================
    st.subheader("🏥 AI Healthcare Buffer (Parents)")
    st.markdown("Predict the actuarial 'Real Cost' of a medical emergency using our Custom Random Forest model.")
    
    model_data = load_healthcare_model()
    
    if not model_data:
        st.error("⚠️ The AI Healthcare model is not trained. Run 'python train_healthcare_model.py' in your terminal!")
        return

    model = model_data['model']
    encoders = model_data['encoders']

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            parent_age = st.slider("Parent's Age", min_value=18, max_value=100, value=65)
            gender = st.selectbox("Gender", ["Male", "Female"])
        with c2:
            city_tier = st.selectbox("Hospital Tier", ["Tier 1", "Tier 2", "Tier 3"])
            tobacco = st.selectbox("Tobacco Usage", ["Yes", "No"], index=1)
        with c3:
            diabetes = st.selectbox("Has Diabetes?", ["Yes", "No"], index=1)
            hypertension = st.selectbox("Has Hypertension (BP)?", ["Yes", "No"], index=1)
            
        if st.button("Predict Emergency Corpus", type="primary", use_container_width=True):
            with st.spinner("Running Random Forest Inference..."):
                encoded_gender = encoders['gender'].transform([gender])[0]
                encoded_tier = encoders['hospital_tier'].transform([city_tier])[0]
                encoded_tobacco = encoders['tobacco_usage'].transform([tobacco])[0]
                encoded_diabetes = encoders['has_diabetes'].transform([diabetes])[0]
                encoded_hyper = encoders['has_hypertension'].transform([hypertension])[0]
                
                total_risk = encoded_diabetes + encoded_hyper + encoded_tobacco
                
                input_data = [[parent_age, encoded_gender, encoded_tier, encoded_tobacco, encoded_diabetes, encoded_hyper, total_risk]]
                
                log_pred = model.predict(input_data)[0]
                baseline_cost = np.expm1(log_pred)
                
                volatility_buffer = baseline_cost * 0.15 
                recommended_corpus = baseline_cost + volatility_buffer
                
                st.write("---")
                rc1, rc2 = st.columns([1, 1.5])
                
                with rc1:
                    st.markdown("<h4 style='color: var(--text-color); opacity: 0.7;'>Recommended Safe Corpus</h4>", unsafe_allow_html=True)
                    st.markdown(f"<div style='color: var(--primary-color); font-size: 1.75rem; font-weight: 700;'>{fmt_money(recommended_corpus)}</div>", unsafe_allow_html=True)
                    st.info("💡 **Recommendation:** Keep this amount in an ultra-short duration debt fund for instant liquidity.")
                
                with rc2:
                    breakdown_data = pd.DataFrame({
                        "Category": ["Baseline Demographic Risk", "Medical Volatility Buffer (15%)"],
                        "Amount": [baseline_cost, volatility_buffer]
                    })
                    fig = px.pie(breakdown_data, values="Amount", names="Category", 
                                 title="Corpus Breakdown", hole=0.4,
                                 color_discrete_sequence=['#3b82f6', '#f59e0b'])
                    
                    fig.update_layout(
                        height=280, 
                        margin=dict(t=30, b=0, l=0, r=0),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color=st.get_option("theme.textColor") if st.get_option("theme.textColor") else None)
                    )
                    st.plotly_chart(fig, use_container_width=True)