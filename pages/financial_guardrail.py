import hashlib
import os
import secrets
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
from utils.ai_client import get_gemini_client, get_best_model, generate_content_safe
from utils.ai_persona import persona_and_currency_note
from utils.currency import fmt_label, fmt_money

# The webhook URL the Chrome Extension must POST checkouts to.
# Render / local — whichever env var is set, or the Streamlit Cloud default.
_WEBHOOK_URL = os.environ.get(
    "WEBHOOK_URL",
    os.environ.get("INTERCEPT_WEBHOOK_URL", ""),
)

# Initialize AI client
genai_client = get_gemini_client()


def _pairing_code(user_id: str) -> str:
    """Deterministic 6-digit pairing code from user_id — same code every session."""
    h = hashlib.sha256(user_id.encode()).hexdigest()
    return str(int(h[:8], 16) % 1_000_000).zfill(6)

def calculate_probability(target, current, monthly_contrib, months_left):
    """Calculates a rough probability (0-99%) of hitting a goal based on current trajectory."""
    if months_left <= 0: return 99 if current >= target else 5
    projected_final = current + (monthly_contrib * months_left)
    buffer_ratio = projected_final / target
    prob = (buffer_ratio * 80)
    return min(max(int(prob), 5), 99)

@st.dialog("✏️ Edit Goal")
def edit_goal_dialog(goal, supabase):
    with st.form(f"edit_form_{goal['id']}"):
        g_name = st.text_input("Goal Name", value=goal['goal_name'])
        g_target = st.number_input(fmt_label("Target Amount (₹)"), min_value=1000, step=5000, value=int(goal['target_amount']))
        g_saved = st.number_input(fmt_label("Already Saved (₹)"), min_value=0, step=1000, value=int(goal['current_saved']))
        g_monthly = st.number_input(fmt_label("Monthly Contribution (₹)"), min_value=0, step=500, value=int(goal['monthly_contribution']))
        
        existing_date = datetime.strptime(goal['target_date'], "%Y-%m-%d").date()
        g_date = st.date_input("Target Date", value=existing_date)
        
        if st.form_submit_button("Update Goal", type="primary"):
            supabase.table("goals").update({
                "goal_name": g_name,
                "target_amount": g_target,
                "current_saved": g_saved,
                "monthly_contribution": g_monthly,
                "target_date": str(g_date)
            }).eq("id", goal['id']).execute()
            st.success("Goal successfully updated!")
            st.rerun()

@st.dialog("💳 Virtual Card Authorized")
def show_virtual_card(item, price):
    st.balloons()
    st.success(f"The AI Guardrail has authorized the purchase.")
    
    with st.container(border=True):
        st.markdown("### 💳 One-Time Use Virtual Card")
        st.code("4532 • 8812 • 0901 • 4452", language="text")
        c1, c2 = st.columns(2)
        c1.markdown("**EXP:** 05/29")
        c2.markdown("**CVV:** 991")
        st.caption(f"Spending Limit Locked to: {fmt_money(price, dp=2)}")
    
    st.warning("This card will expire automatically in 30 minutes.")

@st.dialog("Delete goal")
def delete_goal_dialog(goal, supabase):
    """Ask before permanently deleting a savings goal."""
    st.warning(f"Permanently delete the goal **{goal['goal_name']}**? "
               "This cannot be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, delete", type="primary", use_container_width=True):
        supabase.table("goals").delete().eq("id", goal['id']).execute()
        st.rerun()
    if c2.button("Cancel", use_container_width=True):
        st.rerun()

def render_page(supabase):
    # ✨ THE FIX: Moved gradient styles to a dedicated CSS class with !important tags
    st.markdown("""
        <div class="page-header">
            <h2>AI Financial Guardrail</h2>
            <p>Generating single-use payment tokens only if your long-term goals remain safe.</p>
        </div>
    """, unsafe_allow_html=True)

    # --- 1. FETCH GOALS ---
    try:
        goals_res = supabase.table("goals").select("*").eq("user_id", st.session_state.user_id).order("created_at").execute()
        goals = goals_res.data
    except Exception as e:
        st.error(f"Failed to fetch goals: {e}")
        return

    st.write("---")
    c1, c2 = st.columns([1, 1.5])
    
    # --- 2. GOAL MANAGEMENT ---
    with c1:
        st.subheader("🎯 Your Active Goals")
        if not goals:
            st.info("No goals set. Create one to enable the Guardrail.")
        else:
            for goal in goals:
                progress = min(goal['current_saved'] / goal['target_amount'], 1.0)
                st.markdown(f"**{goal['goal_name']}**")
                st.progress(progress)
                st.caption(f"{fmt_money(goal['current_saved'])} / {fmt_money(goal['target_amount'])} by {goal['target_date']}")
                
                with st.expander("⚙️ Manage Goal"):
                    mc1, mc2 = st.columns(2)
                    if mc1.button("✏️ Edit", key=f"edit_btn_{goal['id']}", use_container_width=True):
                        edit_goal_dialog(goal, supabase)
                    
                    if mc2.button("❌ Delete", key=f"del_init_{goal['id']}", use_container_width=True):
                        delete_goal_dialog(goal, supabase)
                st.write("")
                
        with st.expander("➕ Create New Goal"):
            with st.form("new_goal_form", clear_on_submit=True):
                g_name = st.text_input("Goal Name (e.g., Europe Trip 2026)")
                g_target = st.number_input(fmt_label("Target Amount (₹)"), min_value=1000, step=5000)
                g_saved = st.number_input(fmt_label("Already Saved (₹)"), min_value=0, step=1000)
                g_monthly = st.number_input(fmt_label("Monthly Contribution (₹)"), min_value=0, step=500)
                g_date = st.date_input("Target Date", min_value=datetime.today())
                
                if st.form_submit_button("Save Goal", type="primary"):
                    if g_name:
                        supabase.table("goals").insert({
                            "user_id": st.session_state.user_id,
                            "goal_name": g_name,
                            "target_amount": g_target,
                            "current_saved": g_saved,
                            "monthly_contribution": g_monthly,
                            "target_date": str(g_date)
                        }).execute()
                        st.rerun()

    # --- 3. THE SMART CHECKOUT GATEKEEPER ---
    with c2:
        st.subheader("🔗 Active Interception Queue")

        # ── 3a. EXTENSION SETUP ─────────────────────────────────────────────
        with st.container(border=True):
            pc_head, pc_btn = st.columns([4, 1])
            with pc_head:
                st.markdown(
                    "<div style='font-weight:700;font-size:.95rem;color:var(--text-color)'>"
                    "Pair Your Browser Extension</div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "The extension needs two values to send intercepted checkouts "
                    "to this app: your **User ID** and the **Webhook URL**. "
                    "Enter both in the extension's settings."
                )
            with pc_btn:
                st.write("")
                if st.button("🔄 New Code", key="new_pair_code", use_container_width=True):
                    new_salt = secrets.token_hex(4)
                    st.session_state["_pair_salt"] = new_salt
                    st.rerun()

            # User ID — the extension must send this in every checkout POST
            uid = st.session_state.user_id
            st.text_input(
                "Your User ID (paste into extension)",
                value=uid,
                disabled=True,
                key="_ext_uid_display",
                help="The extension sends this in every checkout payload.",
            )

            # Webhook URL — the extension POSTs here
            webhook_display = _WEBHOOK_URL if _WEBHOOK_URL else "⚠️ Not configured — set WEBHOOK_URL in your environment"
            st.text_input(
                "Webhook URL (paste into extension)",
                value=webhook_display,
                disabled=True,
                key="_ext_webhook_display",
                help="The Chrome extension POSTs intercepted checkouts to this URL.",
            )

            # Legacy pairing code (kept for backward compat)
            code = _pairing_code(st.session_state.user_id)
            display_code = code if not st.session_state.get("_pair_salt") \
                else str(int(hashlib.sha256(
                    (st.session_state.user_id + st.session_state["_pair_salt"]).encode()
                ).hexdigest()[:8], 16) % 1_000_000).zfill(6)
            st.text_input(
                "Pairing code (legacy — use User ID + Webhook URL instead)",
                value=display_code,
                disabled=True,
                key="_ext_code_display",
            )

            # Connection status — check for recent checkouts (last 1 h) rather
            # than just querying the table (which always succeeds if the table
            # exists, even when the extension has never sent anything).
            try:
                one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
                ext_res = (
                    supabase.table("pending_checkouts")
                    .select("id")
                    .eq("user_id", uid)
                    .gte("created_at", one_hour_ago)
                    .limit(1)
                    .execute()
                )
                has_recent = bool(ext_res.data)
            except Exception:
                has_recent = False

            if has_recent:
                st.success(
                    "🟢 Extension is connected — intercepted checkouts are "
                    "appearing in the queue below.",
                    icon="✅",
                )
            elif not _WEBHOOK_URL:
                st.warning(
                    "⚪ **Webhook URL not configured.** Set `WEBHOOK_URL` in "
                    "your environment (e.g. `https://your-app.onrender.com`) "
                    "so the extension knows where to send checkouts."
                )
            else:
                st.info(
                    "⚪ Extension not yet paired. Open the FinGuru Chrome "
                    "Extension settings, paste your **User ID** and **Webhook "
                    "URL** above, then visit an e-commerce checkout page."
                )

        st.write("")

        # ── 3b. INTERCEPTION QUEUE ─────────────────────────────────────────────
        col_title, col_sync = st.columns([2, 1])
        if col_sync.button("🔄 Sync with Extension", use_container_width=True):
            st.rerun()

        with st.container(border=True):
            try:
                pending_res = supabase.table("pending_checkouts").select("*").eq("user_id", st.session_state.user_id).eq("status", "pending_ai_review").order("created_at", desc=True).limit(1).execute()
                pending_requests = pending_res.data
            except Exception as e:
                pending_requests = []

            if pending_requests:
                latest_request = pending_requests[0]
                product_url = latest_request['product_url']
                request_id = latest_request['id']
                
                st.success("🚨 **Checkout Intercepted!**")
                
                short_url = product_url[:50] + "..." if len(product_url) > 50 else product_url
                st.markdown(f"**Link:** [{short_url}]({product_url})")
                
                live_price = latest_request.get('product_price', 0.0)
                if live_price is None: live_price = 0.0
                final_price = st.number_input(fmt_label("Confirmed Item Price (₹)"), min_value=0.0, step=100.0, value=float(live_price))
                
                if goals:
                    impact_goal = st.selectbox("Anchor Goal", [g['goal_name'] for g in goals])
                    c_req, c_clear = st.columns([2, 1])
                    request_btn = c_req.button("🔓 Request AI Authorization", type="primary", use_container_width=True)
                    if c_clear.button("🗑️ Clear Request", use_container_width=True):
                        supabase.table("pending_checkouts").update({"status": "cancelled"}).eq("id", request_id).execute()
                        st.rerun()
                else:
                    st.warning("Please create a goal on the left first.")
                    request_btn = False
            else:
                st.info("⏳ Queue is empty. Waiting for browser extension intercept...")
                request_btn = False

    # --- 4. REAL-TIME PROBABILITY INTERVENTION ---
    if request_btn and final_price > 0:
        target_goal = next(g for g in goals if g['goal_name'] == impact_goal)
        target_date = datetime.strptime(target_goal['target_date'], "%Y-%m-%d").date()
        months_left = max((target_date.year - datetime.today().year) * 12 + target_date.month - datetime.today().month, 1)
        
        base_prob = calculate_probability(target_goal['target_amount'], target_goal['current_saved'], target_goal['monthly_contribution'], months_left)
        new_prob = calculate_probability(target_goal['target_amount'], target_goal['current_saved'] - final_price, target_goal['monthly_contribution'], months_left)
        
        st.write("---")
        st.subheader("🤖 Guardrail Decision Matrix")
        
        c_prob, c_ai = st.columns([1, 1.5])
        
        with c_prob:
            fig = go.Figure(go.Indicator(
                mode = "gauge+number+delta",
                value = new_prob,
                delta = {'reference': base_prob},
                title = {'text': "Goal Probability", 'font': {'size': 20}},
                gauge = {
                    'axis': {'range': [0, 100], 'tickcolor': "rgba(150,150,150,0.5)"}, 
                    'bar': {'color': "#3b82f6" if new_prob > 70 else "#ef4444"},
                    'bgcolor': "rgba(0,0,0,0)",
                    'borderwidth': 2,
                    'bordercolor': "rgba(150,150,150,0.2)"
                }
            ))
            fig.update_layout(
                height=300, 
                margin=dict(t=50, b=10, l=10, r=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=st.get_option("theme.textColor") if st.get_option("theme.textColor") else "gray")
            )
            st.plotly_chart(fig, use_container_width=True)

        with c_ai:
            with st.spinner("Analyzing financial impact..."):
                try:
                    target_model = get_best_model(genai_client, prefer_flash=True)
                    model = genai_client.GenerativeModel(target_model)
                    prompt = (f"{persona_and_currency_note()}\n\n"
                  f"Analyze: Spending {fmt_money(final_price)} on product from {product_url}. "
                  f"Goal: {target_goal['goal_name']}. Probability drops from {base_prob}% to "
                  f"{new_prob}%. Give a short, brutal financial reality check.")

                    response_text = generate_content_safe(model, prompt)

                    if response_text:
                        st.markdown(f"### AI Verdict\n{response_text}")

                        st.write("")
                        if new_prob < 50:
                            st.error("🚨 **Authorization Denied.** This purchase puts your long-term security at risk.")
                            if st.button("Request Human Override"):
                                st.warning("Override request sent to your backup financial buddy.")
                        else:
                            st.success("✅ **Authorization Possible.** Your trajectory remains stable.")
                            if st.button("Generate Virtual Card"):
                                supabase.table("pending_checkouts").update({"status": "approved"}).eq("id", request_id).execute()
                                show_virtual_card(target_goal['goal_name'], final_price)
                    else:
                        raise Exception("Empty response from model")

                except Exception as e:
                    st.error(f"❌ AI Logic Error: {str(e)}")