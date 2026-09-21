import { CashflowChart } from "@/components/charts/CashflowChart";
import { Gauge } from "@/components/ui/Gauge";
import { Panel } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatCard } from "@/components/ui/StatCard";

const DEMO_CASHFLOW = [
  { month: "Feb", value: 42000 },
  { month: "Mar", value: -5200 },
  { month: "Apr", value: 38500 },
  { month: "May", value: -11800 },
  { month: "Jun", value: 44200 },
  { month: "Jul", value: 3400 },
  { month: "Aug", value: -7600 },
  { month: "Sep", value: 46100 },
];

export function TrackPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Dashboard</h1>
        <p className="mt-1 text-sm text-muted">
          Component-library preview with demo data — live data arrives in Phase 4.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard label="Net worth" value="₹12,40,500" delta={2.4} deltaLabel="vs last month" />
        <StatCard
          label="Monthly spend"
          value="₹38,210"
          delta={5.1}
          deltaLabel="vs last month"
          positiveIsGood={false}
        />
        <StatCard label="Safe-to-spend" value="₹1,240 / day" delta={-3.2} deltaLabel="vs last week" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Monthly net cashflow" className="lg:col-span-2">
          <CashflowChart data={DEMO_CASHFLOW} />
        </Panel>
        <div className="space-y-4">
          <Panel title="Budget — September">
            <ProgressBar label="Monthly budget used" value={26150} max={40000} />
          </Panel>
          <Panel title="Financial health">
            <Gauge value={74} max={100} label="Good — a few levers left" />
          </Panel>
        </div>
      </div>
    </div>
  );
}
