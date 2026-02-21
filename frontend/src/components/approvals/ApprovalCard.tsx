import { useState } from 'react'
import clsx from 'clsx'
import { ChevronDown, ChevronUp } from 'lucide-react'
import ConfidenceBadge from '../shared/ConfidenceBadge'
import { ACTION_COLORS } from '../../lib/constants'
import type { TradeDecision } from '../../lib/types'

interface ApprovalCardProps {
  trade: TradeDecision
  onApprove: (id: number) => void
  onReject: (id: number) => void
  isPending: boolean
}

export default function ApprovalCard({ trade, onApprove, onReject, isPending }: ApprovalCardProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={clsx(
      'card border transition-colors',
      trade.wash_sale_flagged ? 'border-warning/40' : 'border-border'
    )}>
      <div className="flex items-start justify-between gap-4">
        {/* Left: ticker info */}
        <div className="flex items-center gap-3 min-w-0">
          <span className={clsx('text-xs font-mono px-2 py-1 rounded', ACTION_COLORS[trade.action])}>
            {trade.action}
          </span>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-text-primary font-mono font-semibold text-lg">{trade.ticker}</span>
              <span className="text-text-muted text-xs font-mono">{trade.sleeve}</span>
              {trade.wash_sale_flagged && (
                <span className="text-warning text-xs" title="Wash sale window active — cost basis will be adjusted">
                  ⚠ wash sale
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-0.5">
              <ConfidenceBadge value={trade.confidence} />
              <span className="text-text-muted text-xs font-mono">
                {trade.position_size_pct.toFixed(1)}% of sleeve
              </span>
              {trade.stop_loss_pct && (
                <span className="text-text-muted text-xs font-mono">
                  SL {trade.stop_loss_pct}%
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right: action buttons */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => onReject(trade.id)}
            disabled={isPending}
            className="btn-danger text-xs py-1.5 px-3 disabled:opacity-50"
          >
            Reject
          </button>
          <button
            onClick={() => onApprove(trade.id)}
            disabled={isPending}
            className="btn-primary text-xs py-1.5 px-3 disabled:opacity-50"
          >
            Approve
          </button>
        </div>
      </div>

      {/* Expandable reasoning */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-3 flex items-center gap-1 text-text-muted text-xs hover:text-text-secondary transition-colors"
      >
        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        {expanded ? 'Hide' : 'Show'} reasoning
      </button>

      {expanded && (
        <div className="mt-2 p-3 bg-bg rounded text-text-secondary text-xs leading-relaxed font-mono whitespace-pre-wrap border border-border">
          {trade.reasoning}
        </div>
      )}
    </div>
  )
}
