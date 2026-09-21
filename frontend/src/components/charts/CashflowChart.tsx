import { useId } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_COLORS, GAIN_GRADIENT_STOPS, LOSS_GRADIENT_STOPS } from "@/lib/chart";

export interface CashflowPoint {
  month: string;
  value: number;
}

interface CashflowChartProps {
  data: CashflowPoint[];
  height?: number;
}

export function CashflowChart({ data, height = 256 }: CashflowChartProps) {
  // useId() returns ":r1:"-style ids whose colons break SVG url(#...) references.
  const gainId = `gain-${useId().replace(/:/g, "")}`;
  const lossId = `loss-${useId().replace(/:/g, "")}`;

  // Split the fill at the zero line: green area above zero, red below it.
  const series = data.map((point) => ({
    ...point,
    gain: Math.max(point.value, 0),
    loss: Math.min(point.value, 0),
  }));

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={gainId} x1="0" y1="0" x2="0" y2="1">
              {GAIN_GRADIENT_STOPS.map((stop) => (
                <stop
                  key={stop.offset}
                  offset={stop.offset}
                  stopColor={stop.color}
                  stopOpacity={stop.opacity}
                />
              ))}
            </linearGradient>
            <linearGradient id={lossId} x1="0" y1="0" x2="0" y2="1">
              {LOSS_GRADIENT_STOPS.map((stop) => (
                <stop
                  key={stop.offset}
                  offset={stop.offset}
                  stopColor={stop.color}
                  stopOpacity={stop.opacity}
                />
              ))}
            </linearGradient>
          </defs>
          <CartesianGrid stroke={CHART_COLORS.edge} vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fill: CHART_COLORS.muted, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: CHART_COLORS.edge }}
          />
          <YAxis
            tick={{ fill: CHART_COLORS.muted, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <Tooltip
            cursor={{ stroke: CHART_COLORS.edge }}
            contentStyle={{
              background: CHART_COLORS.surface,
              border: `1px solid ${CHART_COLORS.edge}`,
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: CHART_COLORS.muted }}
            itemStyle={{ color: CHART_COLORS.ink }}
            formatter={(value) => `₹${Number(value).toLocaleString("en-IN")}`}
          />
          <Area
            type="monotone"
            dataKey="gain"
            stroke={CHART_COLORS.accent}
            strokeWidth={2}
            fill={`url(#${gainId})`}
          />
          <Area
            type="monotone"
            dataKey="loss"
            stroke={CHART_COLORS.danger}
            strokeWidth={2}
            fill={`url(#${lossId})`}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
