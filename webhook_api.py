from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone  # anomaly timestamp (IST-aware)
IST = timezone(timedelta(hours=5, minutes=30))
from utils.anomaly_engine import check_and_alert_anomaly  # ✨ NEW: Import your anomaly engine

load_dotenv()

# Initialize Supabase
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

app = FastAPI()

# Configure CORS to allow your Chrome Extension to talk to this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from any website (like amazon.in)
    allow_credentials=True,
    allow_methods=["*"],  # Allows POST, GET, and OPTIONS requests
    allow_headers=["*"],
)

# This defines the exact data Chrome will send us
class CheckoutRequest(BaseModel):
    user_id: str
    product_url: str
    product_price: float

@app.post("/intercept")
async def intercept_checkout(req: CheckoutRequest):
    try:
        # 1. Log the intercepted checkout to the database
        supabase.table("pending_checkouts").insert({
            "user_id": req.user_id,
            "product_url": req.product_url,
            "product_price": req.product_price,
            "status": "pending_ai_review"
        }).execute()

        # ✨ NEW: 2. Fetch the user's profile to get their email and name
        user_res = supabase.table("profiles").select("email, full_name").eq("id", req.user_id).execute()
        
        if user_res.data:
            user_email = user_res.data[0].get("email")
            
            # Safely grab the first name, default to "User" if missing
            raw_name = user_res.data[0].get("full_name")
            user_name = raw_name.split(" ")[0] if raw_name else "User"
            
            # ✨ NEW: 3. Run the instant anomaly check!
            check_and_alert_anomaly(
                supabase=supabase,
                user_id=req.user_id,
                user_email=user_email,
                user_name=user_name,
                amount=req.product_price,
                category="Shopping", # Default category for e-commerce intercepts
                description=req.product_url,
                transaction_time_iso=datetime.now(IST).isoformat(),
                account_name="E-Commerce Intercept" # So the user knows it came from the Chrome Extension
            )

        return {"status": "success"}
    except Exception as e:
        print(f"Webhook Error: {e}") # Print to Render logs for easy debugging
        return {"status": "error", "message": str(e)}