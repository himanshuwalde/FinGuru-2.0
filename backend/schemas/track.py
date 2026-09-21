from typing import Literal

from pydantic import BaseModel


class MonthPoint(BaseModel):
    month: str
    income: float
    expense: float
    net: float


class KpiValue(BaseModel):
    value: float
    mom_pct: float | None = None


class HealthFlag(BaseModel):
    severity: Literal["positive", "warning", "danger"]
    message: str


class HealthBrief(BaseModel):
    overall: int
    verb: str
    flags: list[HealthFlag]


class BudgetPanel(BaseModel):
    monthly_budget: float
    spent: float
    percent_used: float
    status: Literal["none", "ok", "warning", "over"]


class DashboardResponse(BaseModel):
    display_name: str
    month_label: str
    net_worth: float
    income: KpiValue
    expense: KpiValue
    net: KpiValue
    health: HealthBrief
    budget: BudgetPanel
    cashflow: list[MonthPoint]
