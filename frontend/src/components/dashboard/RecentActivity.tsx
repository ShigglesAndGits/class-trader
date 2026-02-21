import clsx from 'clsx'
import { ACTION_COLORS } from '../../lib/constants'
import { formatTime } from '../../lib/utils'

interface Decision {
  id: number
  ticker: string
  sleeve: string
  action: string
  confidence: number
  status: string
  wash_sale_flagged: boolean
  created_at: string
  resolved_by: string | null
}

interface RecentActivityProps {
  decisions: Decision[]
}

const STATUS_COLOR: Record<string, string> = {
  PENDING: 'text-warning',
  APPROVED: 'text-gain',
  REJECTED: 'text-loss',
  EXECUTED: 'text-gain',
  FAILED: 'text-loss',
  SKIPPED: 'text-text-muted',
}

export default function RecentActivity({ decisions }: RecentActivityProps) {
  if (decisions.length === 0) {
    return (
      <div className="text-text-muted text-sm py-6 text-center">
        No agent decisions in the last 24 hours.
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {decisions.map((d) => (
        <div
          key={d.id}
          className="flex items-center justify-between py-2 border-b border-border last:border-0"
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className={clsx('text-xs font-mono px-1.5 py-0.5 rounded', ACTION_COLORS[d.action])}>
              {d.action}
            </span>
            <span className="font-mono text-text-primary text-sm font-semibold">{d.ticker}</span>
            {d.wash_sale_flagged && (
              <span className="text-warning text-xs" title="Wash sale window active">⚠</span>
            )}
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <span className={clsx('text-xs font-mono', STATUS_COLOR[d.status] ?? 'text-text-muted')}>
              {d.status}
            </span>
            <span className="text-text-muted text-xs font-mono">
              {formatTime(d.created_at)}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
