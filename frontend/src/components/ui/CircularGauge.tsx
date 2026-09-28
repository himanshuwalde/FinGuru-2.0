import { cn } from '@/lib/cn'

interface CircularGaugeProps {
  value: number
  label: string
  size?: number
  strokeWidth?: number
  className?: string
  showValue?: boolean
  max?: number
  color?: 'green' | 'red' | 'blue' | 'amber'
}

const COLORS = {
  green: 'var(--color-accent-green)',
  red: 'var(--color-accent-red)',
  blue: 'var(--color-accent-blue)',
  amber: '#f59e0b',
}

export function CircularGauge({
  value,
  label,
  size = 120,
  strokeWidth = 8,
  className,
  showValue = true,
  max = 100,
  color = 'green',
}: CircularGaugeProps) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const progress = Math.max(0, Math.min(1, value / max))
  const strokeDashoffset = circumference * (1 - progress)
  const strokeColor = COLORS[color]

  return (
    <div className={cn('flex flex-col items-center', className)}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="transform -rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--color-border)"
            strokeWidth={strokeWidth}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={strokeColor}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            style={{
              transition: 'stroke-dashoffset 0.8s ease-out',
            }}
          />
        </svg>
        {showValue && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xl font-bold text-[var(--color-text-primary)] font-numeric">
              {Math.round(value)}
            </span>
          </div>
        )}
      </div>
      <p className="mt-3 text-sm text-[var(--color-text-secondary)] text-center max-w-[140px]">
        {label}
      </p>
    </div>
  )
}