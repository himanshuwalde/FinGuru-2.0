import { cn } from '@/lib/utils'

interface StatCardProps {
  label: string
  value: string | number
  delta?: string | number
  deltaColor?: 'green' | 'red' | 'neutral'
  trend?: 'up' | 'down' | 'neutral'
  icon?: React.ReactNode
  className?: string
}

export function StatCard({
  label,
  value,
  delta,
  deltaColor = 'neutral',
  trend = 'neutral',
  icon,
  className,
}: StatCardProps) {
  const deltaColors = {
    green: 'text-[var(--color-accent-green)]',
    red: 'text-[var(--color-accent-red)]',
    neutral: 'text-[var(--color-text-secondary)]',
  }

  const trendColors = {
    up: 'bg-[var(--color-accent-green)]',
    down: 'bg-[var(--color-accent-red)]',
    neutral: 'bg-[var(--color-text-secondary)]',
  }

  return (
    <div
      className={cn(
        'card p-5 flex flex-col',
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wide mb-1">
            {label}
          </p>
          <p className="text-2xl font-bold text-[var(--color-text-primary)] font-numeric truncate">
            {value}
          </p>
        </div>
        {icon && (
          <div className="ml-3 flex-shrink-0 text-[var(--color-text-secondary)]">
            {icon}
          </div>
        )}
      </div>

      {(delta !== undefined || trend !== 'neutral') && (
        <div className="mt-3 flex items-center gap-2">
          {delta !== undefined && (
            <span className={cn('text-sm font-medium', deltaColors[deltaColor])}>
              {typeof delta === 'string' ? delta : `${delta >= 0 ? '+' : ''}${delta}%`}
            </span>
          )}
          <span
            className={cn(
              'w-1.5 h-1.5 rounded-full',
              trendColors[trend]
            )}
          />
        </div>
      )}
    </div>
  )
}
