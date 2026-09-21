import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import joblib
import os
import xgboost as xgb
from utils.security import decrypt_data
from utils.currency import fmt_label, fmt_money, fmt_input_label, to_inr

# Cache the ML model so it only loads into memory once when the app starts!
@st.cache_resource
def load_ml_model():
    model_path = "trust_engine_model.pkl"
    if os.path.exists(model_path):
        return joblib.load(model_path)
    return None

def render_page(supabase):
    # ✨ THE FIX: Moved gradient styles to a dedicated CSS class with !important tags to prevent Streamlit render glitches
    st.markdown("""
        <div class="page-header">
        <h2>Trust Engine (Loan Predictor)</h2>
        <p>Generating a shadow credit score using XGBoost on alternative behavioral data.</p>
    </div>
    """, unsafe_allow_html=True)

    # Load Model
    model = load_ml_model()
    if model is None:
        st.error("⚠️ **ML Model Not Found!** Please run `train_trust_engine_model.py` to generate the `trust_engine_model.pkl` file.")
        return

    # --- 1. FETCH, FILTER & DECRYPT DATA ---
    try:
        acc_response = supabase.table("accounts").select("*").eq("user_id", st.session_state.user_id).order("created_at").execute()
        user_accounts = acc_response.data
        
        primary_acc = next((acc for acc in user_accounts if acc.get('is_primary')), None)
        if not primary_acc:
            if len(user_accounts) > 0:
                primary_acc = user_accounts[0]
            else:
                st.warning("📊 You need to add a Bank Account in the Dashboard before generating a Trust Score!")
                return
        
        account_id = primary_acc['id']

        trans_res = supabase.table("transactions").select("*").eq("user_id", st.session_state.user_id).execute()
        all_transactions = trans_res.data
        
        account_transactions = [t for t in all_transactions if t.get('account_id') == account_id]

    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        return

    if not account_transactions or len(account_transactions) == 0:
        st.info(f"📊 Not enough data in your primary account ({primary_acc['account_name']}) to generate a Trust Score.")
        return

    df = pd.DataFrame(account_transactions)
    df['amount'] = pd.to_numeric(df['amount'])
    df['transaction_time'] = pd.to_datetime(df['transaction_time'], format='ISO8601', utc=True).dt.tz_localize(None)
    
    # --- 2. LIVE FEATURE ENGINEERING ---
    income_df = df[df['type'] == 'Income']
    expense_df = df[df['type'] == 'Expense']
    
    total_income = income_df['amount'].sum() if not income_df.empty else 0
    total_expense = expense_df['amount'].sum() if not expense_df.empty else 0
    
    savings_ratio = (total_income - total_expense) / total_income if total_income > 0 else 0
    
    utilities_df = df[df['category'] == 'Utilities']
    utility_count = len(utilities_df)
    
    disc_df = df[df['category'].isin(['Entertainment', 'Food & Dining', 'Shopping'])]
    total_disc = disc_df['amount'].sum()
    disc_ratio = total_disc / total_expense if total_expense > 0 else 0
    
    min_date = df['transaction_time'].min()
    maturity_days = (datetime.now() - min_date).days if pd.notnull(min_date) else 0

    # --- 3. THE XGBOOST PREDICTION ---
    live_features = pd.DataFrame({
        'savings_ratio': [savings_ratio],
        'utility_count': [utility_count],
        'disc_ratio': [disc_ratio],
        'maturity_days': [maturity_days]
    })

    default_probability = model.predict_proba(live_features)[0][1] 
    trust_score = int(900 - (default_probability * 600))

    # --- 4. THE UI DASHBOARD ---
    st.write("---")
    
    col_chart, col_metrics = st.columns([1.2, 1])
    
    with col_chart:
        st.subheader("Shadow Credit Score")
        st.caption(f"Based on your primary account: **{primary_acc['account_name']}**")
        
        # ✨ IMPROVED GAUGE: Brighter colors and thicker arcs
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = trust_score,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "AI Trust Score", 'font': {'size': 24, 'color': 'gray'}},
            gauge = {
                'axis': {'range': [300, 900], 'tickwidth': 1, 'tickcolor': "rgba(150,150,150,0.5)"},
                'bar': {'color': "#FFFFFF", 'thickness': 0.15}, # Pure white indicator needle
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 2,
                'bordercolor': "rgba(150,150,150,0.2)",
                'steps': [
                    {'range': [300, 550], 'color': '#FF3131'}, # Bright Neon Red
                    {'range': [550, 700], 'color': '#FFD700'}, # Bright Gold
                    {'range': [700, 900], 'color': '#39FF14'}],# Bright Neon Green
                'threshold': {
                    'line': {'color': "#2563EB", 'width': 4},
                    'thickness': 0.75,
                    'value': trust_score}
            }
        ))
        
        fig.update_layout(
            height=350, 
            margin=dict(l=20, r=20, t=50, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=st.get_option("theme.textColor") if st.get_option("theme.textColor") else None)
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_metrics:
        st.subheader("ML Feature Weights")
        st.markdown("Live features fed into the XGBoost model:")
        
        st.caption(f"Liquidity Buffer ({(savings_ratio*100):.1f}%)")
        st.progress(min(max(savings_ratio, 0), 1.0))
        
        st.caption(f"Utility Punctuality ({utility_count} payments)")
        st.progress(min(utility_count / 10, 1.0)) 
        
        st.caption(f"Discretionary Restraint ({(1-disc_ratio)*100:.1f}%)")
        st.progress(min(max(1-disc_ratio, 0), 1.0))
        
        st.info("🧠 **Model Active:** XGBoost Inference Engine live.")

    st.write("---")

    # --- 5. DYNAMIC LOAN ELIGIBILITY CALCULATOR ---
    st.subheader("🔮 Advanced Loan Eligibility Predictor")
    st.markdown("Predict approval probability based on your AI Trust Score.")

    with st.container(border=True):
        c1, c2 = st.columns(2)
        
        with c1:
            loan_type = st.selectbox("Loan Type", ["Home Loan", "Personal Loan", "Vehicle Loan", "Gold Loan", "Business Loan", "Consumer Durable Loan", "Credit Card Loan"])
            loan_amount = st.number_input(fmt_input_label("Desired Loan Amount"), min_value=10000, max_value=50000000, value=500000, step=50000)
            tenure_years = st.slider("Loan Tenure (Years)", 1, 30, 5)

        with c2:
            monthly_income = st.number_input(fmt_input_label("Monthly Income"), min_value=5000, value=50000, step=5000)
            existing_emis = st.number_input(fmt_input_label("Existing Monthly EMIs"), min_value=0, value=0, step=1000)
            cibil_score = st.number_input("CIBIL Score (Optional)", min_value=0, max_value=900, value=0, step=1)

        if st.button("Predict Approval Probability", type="primary", use_container_width=True):
            # Convert inputs from user's display currency to INR for calculations
            loan_inr = to_inr(loan_amount)
            income_inr = to_inr(monthly_income)
            emis_inr = to_inr(existing_emis)

            # --- REAL WORLD FINANCIAL MATH UPDATE ---
            rates = {"Home Loan": 8.5, "Vehicle Loan": 9.5, "Gold Loan": 10.0, "Consumer Durable Loan": 12.0, "Personal Loan": 14.0, "Business Loan": 16.0, "Credit Card Loan": 36.0}
            is_secured = loan_type in ["Home Loan", "Vehicle Loan", "Gold Loan"]

            annual_rate = rates.get(loan_type, 12.0)
            monthly_rate = (annual_rate / 100) / 12
            n_months = tenure_years * 12

            # Calculate Standard EMI
            if monthly_rate > 0:
                emi = (loan_inr * monthly_rate * ((1 + monthly_rate)**n_months)) / (((1 + monthly_rate)**n_months) - 1)
            else:
                emi = loan_inr / n_months

            # Calculate Fixed Obligation to Income Ratio (FOIR)
            foir = (emi + emis_inr) / income_inr if income_inr > 0 else 1.0

            # 1. EFFECTIVE SCORE LOGIC
            if cibil_score == 0 or cibil_score == -1:
                # NTC (New to Credit): Rely strictly on AI Trust Score, but apply a 15% risk haircut.
                effective_score = trust_score * 0.85
            elif cibil_score < 300:
                # Invalid fallback
                effective_score = trust_score
            else:
                # Valid CIBIL exists: Blend traditional with alternative (70/30 weighting is standard)
                effective_score = (cibil_score * 0.70) + (trust_score * 0.30)

            # 2. BASE PROBABILITY (Curve based on Effective Score)
            if effective_score >= 750:
                base_prob = 95
            elif effective_score >= 700:
                base_prob = 80
            elif effective_score >= 650:
                base_prob = 50
            elif effective_score >= 600:
                base_prob = 20
            else:
                base_prob = 5

            # 3. FOIR RISK MULTIPLIERS
            if foir > 0.65:
                base_prob *= 0.1  # Auto-reject territory for most banks
            elif foir > 0.55:
                base_prob *= 0.4  # Very high risk
            elif foir > 0.45:
                base_prob *= 0.75 # Moderate risk
            elif foir <= 0.35:
                base_prob *= 1.1  # Excellent capacity, boost approval odds

            # 4. SECURED VS UNSECURED BOOST
            if is_secured:
                base_prob *= 1.25 # Secured loans are much easier to approve

            # Clamp between 1% and 99%
            final_prob = min(max(base_prob, 1), 99)

            st.write("---")
            res_c1, res_c2, res_c3 = st.columns(3)
            res_c1.metric(label="Estimated EMI", value=f"{fmt_money(emi)}/mo")
            res_c2.metric(label="Effective AI Score", value=f"{int(effective_score)}")
            
            # Color code the FOIR metric for better UX
            foir_color = "normal" if foir <= 0.50 else "inverse"
            res_c3.metric(label="Debt-to-Income (FOIR)", value=f"{foir*100:.1f}%", delta="High Risk" if foir > 0.55 else None, delta_color=foir_color)

            prob_color = '#39FF14' if final_prob >= 70 else '#FFD700' if final_prob >= 40 else '#FF3131'
            st.markdown(f"<div style='text-align: center; font-size: 2rem; color: {prob_color}; font-weight: 700;'>{int(final_prob)}%</div>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; font-weight: 500; opacity: 0.6;'>Approval Probability</p>", unsafe_allow_html=True)

            if final_prob >= 70:
                st.success("✅ **Status: Approved.** Your Score, income, and low debt burden comfortably support this loan.")
            elif final_prob >= 40:
                if foir > 0.50:
                    st.warning("⚠️ **Status: Manual Review Required.** Your score is decent, but your Debt-to-Income ratio is straining your capacity.")
                else:
                    st.warning("⚠️ **Status: Manual Review Required.** Your application is borderline. Consider improving your Liquidity Buffer to boost your Trust Score.")
            else:
                if foir > 0.60:
                    st.error("❌ **Status: Rejected.** High Risk. Your existing obligations and this new loan consume too much of your income.")
                else:
                    st.error("❌ **Status: Rejected.** Your Effective Score does not meet the minimum threshold for this loan product.")