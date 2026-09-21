import { CHART_COLORS } from "@/lib/chart";

interface GaugeProps {
  value: number;
  min?: number;
  max?: number;
  label?: string;
}

export function Gauge({ value, min = 0, max = 100, label }: GaugeProps) {
  const RADIUS = 52;
  const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
  const ratio = Math.min(1, Math.max(0, (value - min) / (max - min)));
  const color =
    ratio >= 0.75 ? CHART_COLORS.accent : ratio >= 0.5 ? CHART_COLORS.info : CHART_COLORS.danger;

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 120 120" className="size-40">
        <circle
          cx="60"
          cy="60"
          r={RADIUS}
          fill="none"
          stroke={CHART_COLORS.edge}
          strokeWidth="10"
        />
        <circle
          cx="60"
          cy="60"
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${CIRCUMFERENCE * ratio} ${CIRCUMFERENCE}`}
          transform="rotate(-90 60 60)"
        />
        <text
          x="60"
          y="58"
          textAnchor="middle"
          fill={CHART_COLORS.ink}
          style={{ font: "600 22px var(--font-mono)" }}
        >
          {value}
        </text>
        <text
          x="60"
          y="74"
          textAnchor="middle"
          fill={CHART_COLORS.muted}
          style={{ font: "500 10px var(--font-sans)" }}
        >
          of {max}
        </text>
      </svg>
      {label ? <p className="mt-2 text-sm text-muted">{label}</p> : null}
    </div>
  );
}
