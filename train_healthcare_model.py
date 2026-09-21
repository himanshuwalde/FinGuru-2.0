import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
import joblib

print("🚀 Generating Custom Synthetic Dataset...")

# 1. GENERATE PERFECTLY MATCHED DATA
np.random.seed(42)
n_samples = 5000

# Generate features using the EXACT strings from your Streamlit UI
ages = np.random.randint(18, 100, n_samples)
genders = np.random.choice(["Male", "Female"], n_samples)
tiers = np.random.choice(["Tier 1", "Tier 2", "Tier 3"], n_samples)
tobacco = np.random.choice(["Yes", "No"], n_samples, p=[0.3, 0.7]) # 30% smokers
diabetes = np.random.choice(["Yes", "No"], n_samples, p=[0.25, 0.75])
hypertension = np.random.choice(["Yes", "No"], n_samples, p=[0.35, 0.65])

# Mathematical Engine to calculate realistic base costs
base_costs = np.zeros(n_samples)

for i in range(n_samples):
    # Start with a base hospital admission cost
    cost = 45000.0 
    
    # Age penalty (gets exponentially more expensive as you get older)
    if ages[i] > 50:
        cost += (ages[i] - 50) * 2500
        
    # Tier multipliers
    if tiers[i] == "Tier 1": cost *= 1.6
    elif tiers[i] == "Tier 2": cost *= 1.2
    
    # Pre-existing condition penalties
    if tobacco[i] == "Yes": cost += 65000
    if diabetes[i] == "Yes": cost += 45000
    if hypertension[i] == "Yes": cost += 35000
    
    # Add random real-world volatility (± 20%)
    noise = np.random.uniform(0.8, 1.2)
    base_costs[i] = cost * noise

# Create the DataFrame
df = pd.DataFrame({
    'age': ages, 'gender': genders, 'hospital_tier': tiers,
    'tobacco_usage': tobacco, 'has_diabetes': diabetes, 'has_hypertension': hypertension,
    'total_cost': base_costs
})

print("🧹 Encoding and Training Model...")

# 2. ENCODE THE DATA
label_encoders = {}
categorical_cols = ['gender', 'hospital_tier', 'tobacco_usage', 'has_diabetes', 'has_hypertension']

for col in categorical_cols:
    le = LabelEncoder()
    df[col] = le.fit_transform(df[col])
    label_encoders[col] = le

# Feature engineering
df['total_risk_factors'] = df['has_diabetes'] + df['has_hypertension'] + df['tobacco_usage']

X = df[['age', 'gender', 'hospital_tier', 'tobacco_usage', 'has_diabetes', 'has_hypertension', 'total_risk_factors']]
# Log transform for better training
y = np.log1p(df['total_cost']) 

# 3. TRAIN THE MODEL
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = RandomForestRegressor(n_estimators=100, max_depth=15, random_state=42)
model.fit(X_train, y_train)

# 4. EXPORT
export_data = {
    'model': model,
    'encoders': label_encoders,
    'features': X.columns.tolist()
}
joblib.dump(export_data, 'custom_healthcare_model.joblib')

print("✅ Custom Model trained and saved as 'custom_healthcare_model.joblib'!")