import { Minus, TrendingDown, TrendingUp } from "lucide-react";

import { cn } from "@/lib/cn";

export interface StatCardProps {
  label: string;
  value: string;
  delta?: number;
  deltaLabel?: string;
  positiveIsGood?: boolean;
}

export function StatCard({
  label,
  value,
  delta,
  deltaLabel,
  positiveIsGood = true,
}: StatCardProps) {
  const hasDelta = delta !== undefined;
  const good = delta === undefined || delta === 0 ? null : delta > 0 === positiveIsGood;
  const DeltaIcon = !hasDelta || delta === 0 ? Minus : delta > 0 ? TrendingUp : TrendingDown;

  return (
    <div className="rounded-xl border border-edge bg-surface p-5 transition-colors hover:bg-surface-hover">
      <p className="text-xs font-medium uppercase tracking-wider text-muted">{label}</p>
      <p className="numeric mt-2 text-2xl font-semibold text-ink">{value}</p>
      {hasDelta ? (
        <p
          className={cn(
            "mt-1 flex items-center gap-1 text-xs",
            good === null ? "text-muted" : good ? "text-accent" : "text-danger",
          )}
        >
          <DeltaIcon className="size-3" />
          <span className="numeric">{Math.abs(delta ?? 0).toFixed(1)}%</span>
          {deltaLabel ? <span className="text-muted">{deltaLabel}</span> : null}
        </p>
      ) : null}
    </div>
  );
}
