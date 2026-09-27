import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface MonthPoint {
  month: string;
  income: number;
  expense: number;
  net: number;
}

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

export function useDashboard() {
  return useQuery({
    queryKey: ["track", "dashboard"],
    queryFn: () => apiFetch<DashboardResponse>("/track/dashboard"),
    staleTime: 30_000,
  });
}

export function usePillarStatus(pillar: string) {
  return useQuery({
    queryKey: [pillar, "status"],
    queryFn: () => apiFetch<{ pillar: string; phase: string; modules: string[] }>(`/${pillar}/status`),
    staleTime: 60_000,
  });
}