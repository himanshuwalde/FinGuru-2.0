import { cn } from '@/lib/utils'

interface ProgressBarProps {
  value: number
  max?: number
  label?: string
  showValue?: boolean
  className?: string
  height?: number
  color?: 'green' | 'amber' | 'red'
  segments?: Array<{ value: number; color: string }>
}

const STATUS_COLORS = {
  green: 'var(--color-accent-green)',
  amber: '#f59e0b',
  red: 'var(--color-accent-red)',
}

export function ProgressBar({
  value,
  max = 100,
  label,
  showValue = true,
  className,
  height = 10,
  color = 'green',
  segments,
}: ProgressBarProps) {
  const percent = Math.max(0, Math.min(100, (value / max) * 100))
  const statusColor = segments ? undefined : STATUS_COLORS[color]

  return (
    <div className={cn('w-full', className)}>
      {label && (
        <div className="flex justify-between text-xs mb-1.5">
          <span className="text-[var(--color-text-secondary)]">{label}</span>
          {showValue && (
            <span className="text-[var(--color-text-primary)] font-medium font-numeric">
              {Math.round(value).toLocaleString('en-IN')}
              {max !== 100 && ` / ${Math.round(max).toLocaleString('en-IN')}`}
            </span>
          )}
        </div>
      )}
      <div
        className="relative overflow-hidden rounded-full bg-[var(--color-border)]"
        style={{ height }}
      >
        {segments ? (
          <>
            {segments.map((segment, index) => {
              const segmentPercent = (segment.value / max) * 100
              return (
                <div
                  key={index}
                  className="absolute top-0 h-full"
                  style={{
                    left: `${segments.slice(0, index).reduce((sum, s) => sum + (s.value / max) * 100, 0)}%`,
                    width: `${segmentPercent}%`,
                    backgroundColor: segment.color,
                    transition: 'width 0.5s ease-out',
                  }}
                />
              )
            })}
          </>
        ) : (
          <div
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{
              width: `${percent}%`,
              backgroundColor: statusColor,
            }}
          />
        )}
      </div>
      {showValue && !label && (
        <p className="mt-1 text-xs text-[var(--color-text-secondary)] text-right">
          {Math.round(percent)}%
        </p>
      )}
    </div>
  )
}
