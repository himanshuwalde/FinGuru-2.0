import { cn } from "@/lib/cn";

interface ProgressBarProps {
  label: string;
  value: number;
  max: number;
  formatValue?: (n: number) => string;
}

export function ProgressBar({ label, value, max, formatValue }: ProgressBarProps) {
  const format = formatValue ?? ((n: number) => `₹${n.toLocaleString("en-IN")}`);
  const percent = Math.min(100, Math.round((value / max) * 100));
  const over = value > max;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="numeric text-ink">{percent}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-edge">
        <div
          className={cn("h-full rounded-full transition-all", over ? "bg-danger" : "bg-accent")}
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="numeric mt-2 text-xs text-muted">
        {format(value)} of {format(max)}
      </p>
    </div>
  );
}
