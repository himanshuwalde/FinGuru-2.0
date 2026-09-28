import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { cn } from '@/lib/cn'

interface DataPoint {
  month: string
  income: number
  expense: number
  net: number
}

interface ChartPanelProps {
  title: string
  data: DataPoint[]
  type: 'income' | 'expense' | 'net' | 'cashflow'
  className?: string
  height?: number
  showLegend?: boolean
}

const COLORS = {
  income: 'var(--color-accent-green)',
  expense: 'var(--color-accent-red)',
  net: 'var(--color-accent-blue)',
} as const

const GRADIENTS = {
  gains: "linear-gradient(180deg, rgba(34,197,94,0.35) 0%, rgba(34,197,94,0) 100%)",
  losses: "linear-gradient(180deg, rgba(239,68,68,0.35) 0%, rgba(239,68,68,0) 100%)",
}

export function ChartPanel({
  title,
  data,
  type,
  className,
  height = 220,
  showLegend = false,
}: ChartPanelProps) {
  const isCashflow = type === 'cashflow'
  const seriesColor = isCashflow ? 'var(--color-accent-blue)' : COLORS[type]

  return (
    <div className={cn('card p-5', className)}>
      {title && (
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-4">
          {title}
        </h3>
      )}
      <div className="chart-container" style={{ height }}>
        {isCashflow ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="gradient-income" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgba(34,197,94,0.35)" />
                  <stop offset="100%" stopColor="rgba(34,197,94,0)" />
                </linearGradient>
                <linearGradient id="gradient-expense" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgba(239,68,68,0.35)" />
                  <stop offset="100%" stopColor="rgba(239,68,68,0)" />
                </linearGradient>
              </defs>
              <CartesianGrid
                stroke="var(--color-border)"
                strokeDasharray="4 4"
                vertical={false}
              />
              <XAxis
                dataKey="month"
                tick={{ fill: 'var(--color-text-secondary)', fontSize: 11, fontFamily: 'var(--font-sans)' }}
                axisLine={{ stroke: 'var(--color-border)' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: 'var(--color-text-secondary)', fontSize: 11, fontFamily: 'var(--font-numeric)' }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(value) => value >= 1e5 ? `₹${(value/1e5).toFixed(0)}L` : value >= 1e3 ? `₹${(value/1e3).toFixed(0)}K` : `₹${value}`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--color-bg-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '8px',
                  fontFamily: 'var(--font-sans)',
                }}
                labelStyle={{ color: 'var(--color-text-secondary)', fontSize: '11px' }}
                itemStyle={{ color: 'var(--color-text-primary)', fontSize: '13px' }}
                formatter={(value: number) => [
                  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value),
                  '',
                ]}
              />
              {showLegend && (
                <Legend
                  wrapperStyle={{ paddingTop: '10px' }}
                  formatter={(value) => value}
                />
              )}
              <Area
                type="monotone"
                dataKey="income"
                stroke="var(--color-accent-green)"
                strokeWidth={2}
                fill="url(#gradient-income)"
                name="Income"
              />
              <Area
                type="monotone"
                dataKey="expense"
                stroke="var(--color-accent-red)"
                strokeWidth={2}
                fill="url(#gradient-expense)"
                name="Expense"
              />
              <Line
                type="monotone"
                dataKey="net"
                stroke="var(--color-accent-blue)"
                strokeWidth={2}
                strokeDasharray="6 4"
                dot={false}
                name="Net"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <CartesianGrid
                stroke="var(--color-border)"
                strokeDasharray="4 4"
                vertical={false}
              />
              <XAxis
                dataKey="month"
                tick={{ fill: 'var(--color-text-secondary)', fontSize: 11, fontFamily: 'var(--font-sans)' }}
                axisLine={{ stroke: 'var(--color-border)' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: 'var(--color-text-secondary)', fontSize: 11, fontFamily: 'var(--font-numeric)' }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(value) => value >= 1e5 ? `₹${(value/1e5).toFixed(0)}L` : value >= 1e3 ? `₹${(value/1e3).toFixed(0)}K` : `₹${value}`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--color-bg-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '8px',
                  fontFamily: 'var(--font-sans)',
                }}
                labelStyle={{ color: 'var(--color-text-secondary)', fontSize: '11px' }}
                itemStyle={{ color: 'var(--color-text-primary)', fontSize: '13px' }}
                formatter={(value: number) => [
                  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value),
                  '',
                ]}
              />
              {showLegend && (
                <Legend
                  wrapperStyle={{ paddingTop: '10px' }}
                  formatter={(value) => value}
                />
              )}
              <Line
                type="monotone"
                dataKey={type}
                stroke={seriesColor}
                strokeWidth={2}
                dot={false}
                name={type.charAt(0).toUpperCase() + type.slice(1)}
              />
              <Area
                type="monotone"
                dataKey={type}
                stroke={seriesColor}
                strokeWidth={2}
                fill={type === 'income' ? GRADIENTS.gains : GRADIENTS.losses}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}