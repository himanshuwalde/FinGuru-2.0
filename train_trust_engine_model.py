import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

print("Generating High-Fidelity Synthetic Financial Data...")
np.random.seed(42)
n_samples = 5000

# 1. Establish the Ground Truth (75% Repay, 25% Default)
target = np.random.choice([0, 1], size=n_samples, p=[0.75, 0.25])

# 2. Mathematically generate behaviors based on the target outcome
# Good profiles (0): High savings, high utility count, low disc ratio, older accounts
# Risk profiles (1): Low savings, low utility count, high disc ratio, newer accounts
savings_ratio = np.where(target == 0, np.random.normal(0.35, 0.1, n_samples), np.random.normal(0.08, 0.05, n_samples))
utility_count = np.where(target == 0, np.random.poisson(12, n_samples), np.random.poisson(3, n_samples))
disc_ratio = np.where(target == 0, np.random.normal(0.15, 0.1, n_samples), np.random.normal(0.55, 0.15, n_samples))
maturity_days = np.where(target == 0, np.random.normal(1200, 300, n_samples), np.random.normal(150, 80, n_samples))

# 3. Clean the data to fit real-world bounds
savings_ratio = np.clip(savings_ratio, 0.0, 0.8)
utility_count = np.clip(utility_count, 0, 36)
disc_ratio = np.clip(disc_ratio, 0.0, 0.9)
maturity_days = np.clip(maturity_days, 10, 3000)

ml_data = pd.DataFrame({
    'savings_ratio': savings_ratio,
    'utility_count': utility_count,
    'disc_ratio': disc_ratio,
    'maturity_days': maturity_days
})

# 4. Train/Test Split
X_train, X_test, y_train, y_test = train_test_split(ml_data, target, test_size=0.2, random_state=42)

# Handle Class Imbalance mathematically
majority_class = len(y_train[y_train == 0])
minority_class = len(y_train[y_train == 1])
imbalance_ratio = majority_class / minority_class

print("Training XGBoost Shadow Credit Model...")

# 5. Train the Model with Tuned Parameters
model = xgb.XGBClassifier(
    n_estimators=150,             
    max_depth=3, # Shallower depth prevents overfitting on synthetic data                 
    learning_rate=0.05,           
    scale_pos_weight=imbalance_ratio,
    eval_metric='logloss',
    random_state=42
)

model.fit(X_train, y_train)

# 6. Evaluate
predictions = model.predict(X_test)
accuracy = accuracy_score(y_test, predictions)

print("\n--- MODEL DIAGNOSTICS ---")
print(f"Model Accuracy: {accuracy * 100:.2f}%")
print("\nDetailed Report:")
print(classification_report(y_test, predictions))
print("-------------------------\n")

joblib.dump(model, "trust_engine_model.pkl")
print("✅ Success! The 'trust_engine_model.pkl' has been saved and is ready for Streamlit.")