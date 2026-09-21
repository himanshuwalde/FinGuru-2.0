from datetime import datetime

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException

from backend.auth.dependencies import AuthContext, get_auth_context
from backend.schemas.common import PillarStatus
from backend.schemas.track import (
    BudgetPanel,
    DashboardResponse,
    HealthBrief,
    HealthFlag,
    KpiValue,
    MonthPoint,
)
from backend.supabase_client import SupabaseNotConfigured, user_client
from services import recommendation_service
from services.database import DatabaseService

router = APIRouter(prefix="/track", tags=["track"])

_MODULES = [
    "dashboard",
    "transactions_budgeting",
    "safe_to_spend",
    "anomaly_finder",
    "ghost_spend_auditor",
    "account_aggregator",
    "net_worth_tracker",
]

_CASHFLOW_MONTHS = 6


def _mom(current: float, previous: float) -> float | None:
    """% change vs the prior month; None when there is no baseline."""
    if previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100.0, 1)


def _budget_status(monthly_budget: float, percent_used: float) -> str:
    if monthly_budget <= 0:
        return "none"
    if percent_used >= 100:
        return "over"
    if percent_used >= 85:
        return "warning"
    return "ok"


@router.get("/status", response_model=PillarStatus)
def track_status() -> PillarStatus:
    return PillarStatus(pillar="track", modules=_MODULES)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(auth: AuthContext = Depends(get_auth_context)) -> DashboardResponse:
    try:
        client = user_client(auth.access_token)
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail="Database backend is not configured") from exc

    user_id = auth.user.id
    db = DatabaseService(client)
    today = datetime.now()

    accounts = db.get_user_accounts(user_id)
    df = db.get_transactions_dataframe(user_id)

    display_name = "User"
    try:
        display_name = db.get_user_name(user_id)
    except Exception:
        pass
    if display_name == "User" and auth.user.email:
        display_name = auth.user.email.split("@")[0].replace(".", " ").title()

    # --- this month vs previous month KPIs (all accounts combined) ---
    income = expense = 0.0
    prev_income = prev_expense = 0.0
    if not df.empty:
        this_month = df[
            (df["transaction_time"].dt.month == today.month)
            & (df["transaction_time"].dt.year == today.year)
        ]
        income = float(this_month[this_month["type"] == "Income"]["amount"].sum())
        expense = float(this_month[this_month["type"] == "Expense"]["amount"].sum())

        prev = today - relativedelta(months=1)
        prev_month = df[
            (df["transaction_time"].dt.month == prev.month)
            & (df["transaction_time"].dt.year == prev.year)
        ]
        prev_income = float(prev_month[prev_month["type"] == "Income"]["amount"].sum())
        prev_expense = float(prev_month[prev_month["type"] == "Expense"]["amount"].sum())
    net = income - expense
    prev_net = prev_income - prev_expense

    # --- 6-month cashflow series (net crosses zero: chart splits fills) ---
    cashflow: list[MonthPoint] = []
    for offset in range(_CASHFLOW_MONTHS - 1, -1, -1):
        month = today - relativedelta(months=offset)
        if df.empty:
            cashflow.append(MonthPoint(month=month.strftime("%b %Y"), income=0.0, expense=0.0, net=0.0))
            continue
        sub = df[
            (df["transaction_time"].dt.month == month.month)
            & (df["transaction_time"].dt.year == month.year)
        ]
        m_income = float(sub[sub["type"] == "Income"]["amount"].sum())
        m_expense = float(sub[sub["type"] == "Expense"]["amount"].sum())
        cashflow.append(
            MonthPoint(
                month=month.strftime("%b %Y"),
                income=m_income,
                expense=m_expense,
                net=m_income - m_expense,
            )
        )

    # --- budget panel (all accounts combined, matches the Streamlit default) ---
    monthly_budget = float(sum(acc.get("monthly_budget") or 0 for acc in accounts))
    percent_used = (expense / monthly_budget * 100.0) if monthly_budget > 0 else 0.0

    # --- health score + net worth from the single source of truth ---
    context = recommendation_service.build_financial_context(client, user_id)
    hs = context["health_score"]
    kpis = context["kpis"]

    return DashboardResponse(
        display_name=display_name,
        month_label=today.strftime("%B %Y"),
        net_worth=float(kpis["net_worth"]),
        income=KpiValue(value=income, mom_pct=_mom(income, prev_income)),
        expense=KpiValue(value=expense, mom_pct=_mom(expense, prev_expense)),
        net=KpiValue(value=net, mom_pct=_mom(net, prev_net)),
        health=HealthBrief(
            overall=int(hs["overall"]),
            verb=hs["verb"],
            flags=[HealthFlag(**flag) for flag in hs["flags"]],
        ),
        budget=BudgetPanel(
            monthly_budget=monthly_budget,
            spent=expense,
            percent_used=round(percent_used, 1),
            status=_budget_status(monthly_budget, percent_used),
        ),
        cashflow=cashflow,
    )
