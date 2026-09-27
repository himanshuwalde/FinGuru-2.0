import { CashflowChart } from "@/components/charts/CashflowChart";
import { Gauge } from "@/components/ui/Gauge";
import { Panel } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatCard } from "@/components/ui/StatCard";
import { useDashboard } from "@/hooks/useTrack";

function formatINR(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatINRCompact(value: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
    notation: "compact",
  }).format(value);
}

export function TrackPage() {
  const { data, isLoading, error, refetch } = useDashboard();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold text-ink">Dashboard</h1>
          <p className="mt-1 text-sm text-muted">Loading your financial snapshot…</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard label="Net worth" value="—" />
          <StatCard label="Monthly spend" value="—" />
          <StatCard label="Safe-to-spend" value="—" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold text-ink">Dashboard</h1>
        </div>
        <div className="rounded-xl border border-danger/40 bg-danger/10 p-5 text-sm text-danger">
          Failed to load dashboard: {error.message}
          <button
            onClick={() => refetch()}
            className="ml-3 text-xs font-medium underline-offset-2 hover:underline"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const d = data!;
  const netDelta = d.net.mom_pct ?? 0;
  const incomeDelta = d.income.mom_pct ?? 0;
  const expenseDelta = d.expense.mom_pct ?? 0;

  // Convert cashflow to CashflowChart format: { month, value }
  const cashflowData = d.cashflow.map((p) => ({
    month: p.month,
    value: p.net,
  }));

  // Safe-to-spend daily: (monthly_budget - spent - forecasted_bills) / days_left
  // For now use a simple approximation: (budget - spent) / days left in month
  const now = new Date();
  const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const daysLeft = Math.max(1, daysInMonth - now.getDate());
  const remainingBudget = Math.max(0, d.budget.monthly_budget - d.budget.spent);
  const safeToSpendDaily = daysLeft > 0 ? remainingBudget / daysLeft : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink">Dashboard</h1>
          <p className="mt-1 text-sm text-muted">{d.month_label} · {d.display_name}</p>
        </div>
        <button
          onClick={() => refetch()}
          className="rounded-lg border border-edge px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-surface-hover hover:text-ink"
        >
          Refresh
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label="Net worth"
          value={formatINRCompact(d.net_worth)}
          delta={netDelta !== 0 ? netDelta : undefined}
          deltaLabel={netDelta !== 0 ? "vs last month" : undefined}
        />
        <StatCard
          label="Monthly spend"
          value={formatINRCompact(d.expense.value)}
          delta={expenseDelta !== 0 ? expenseDelta : undefined}
          deltaLabel={expenseDelta !== 0 ? "vs last month" : undefined}
          positiveIsGood={false}
        />
        <StatCard
          label="Safe-to-spend"
          value={`${formatINRCompact(safeToSpendDaily)} / day`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Monthly net cashflow" className="lg:col-span-2">
          <CashflowChart data={cashflowData} />
        </Panel>
        <div className="space-y-4">
          <Panel title={`Budget — ${d.month_label}`}>
            <ProgressBar
              label="Monthly budget used"
              value={d.budget.spent}
              max={d.budget.monthly_budget}
            />
            <p className="mt-2 text-xs text-muted">
              {d.budget.status === "over"
                ? `Over budget by ${formatINR(d.budget.spent - d.budget.monthly_budget)}`
                : d.budget.status === "warning"
                ? `Only ${formatINR(d.budget.monthly_budget - d.budget.spent)} remaining`
                : d.budget.status === "ok"
                ? `${formatINR(d.budget.monthly_budget - d.budget.spent)} left this month`
                : "No budget set — click to create one"}
            </p>
          </Panel>
          <Panel title="Financial health">
            <Gauge value={d.health.overall} max={100} label={d.health.verb} />
            <div className="mt-3 space-y-2">
              {d.health.flags.map((flag, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-2 text-xs"
                  style={{ color: flag.severity === "positive" ? "#22c55e" : flag.severity === "warning" ? "#f1c40f" : "#ef4444" }}
                >
                  <span className="shrink-0 mt-0.5">•</span>
                  <span>{flag.message}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
