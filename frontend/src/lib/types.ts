export interface KpiValue {
  value: number;
  mom_pct: number | null;
}

export interface HealthFlag {
  severity: "positive" | "warning" | "danger";
  message: string;
}

export interface HealthBrief {
  overall: number;
  verb: string;
  flags: HealthFlag[];
}

export interface BudgetPanel {
  monthly_budget: number;
  spent: number;
  percent_used: number;
  status: "none" | "ok" | "warning" | "over";
}

export interface MonthPoint {
  month: string;
  income: number;
  expense: number;
  net: number;
}

export interface DashboardResponse {
  display_name: string;
  month_label: string;
  net_worth: number;
  income: KpiValue;
  expense: KpiValue;
  net: KpiValue;
  health: HealthBrief;
  budget: BudgetPanel;
  cashflow: MonthPoint[];
}
