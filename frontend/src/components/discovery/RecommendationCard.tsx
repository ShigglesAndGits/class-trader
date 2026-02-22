import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import clsx from 'clsx'
import { DISCOVERY_ACTION_COLORS } from '../../lib/constants'
import type { DiscoveryRecommendation } from '../../lib/types'

interface Props {
  rec: DiscoveryRecommendation
  index: number
  selected: boolean
  onToggle: (index: number) => void
}

export default function RecommendationCard({ rec, index, selected, onToggle }: Props) {
  const [expanded, setExpanded] = useState(false)
  const badgeClass = DISCOVERY_ACTION_COLORS[rec.action] ?? 'badge-info'

  return (
    <div
      className={clsx(
        'rounded-md border p-3 transition-colors',
        selected ? 'border-info/40 bg-info/5' : 'border-border bg-surface',
      )}
    >
      <div className="flex items-start gap-3">
        {/* Selection checkbox — all stocks selectable; watchlist accepts AVOID too */}
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggle(index)}
          className="mt-0.5 accent-info shrink-0 cursor-pointer"
          aria-label={`Select ${rec.ticker}`}
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-sm font-semibold text-text-primary">{rec.ticker}</span>
            <span className={clsx('badge text-xs', badgeClass)}>{rec.action}</span>
            <span className="text-xs text-text-muted">{(rec.confidence * 100).toFixed(0)}% confidence</span>
            {rec.position_size_pct > 0 && rec.action !== 'AVOID' && (
              <span className="text-xs text-text-muted">{rec.position_size_pct.toFixed(1)}% size</span>
            )}
            <span className="text-xs text-text-muted ml-auto">{rec.suggested_sleeve}</span>
          </div>

          <p className={clsx('text-xs text-text-secondary mt-1.5 leading-relaxed', !expanded && 'line-clamp-2')}>
            {rec.reasoning}
          </p>

          <div className="flex items-center gap-3 mt-1.5">
            {rec.stop_loss_pct && (
              <span className="text-xs text-loss">SL {rec.stop_loss_pct.toFixed(1)}%</span>
            )}
            {rec.take_profit_pct && (
              <span className="text-xs text-gain">TP {rec.take_profit_pct.toFixed(1)}%</span>
            )}
            <button
              onClick={() => setExpanded(e => !e)}
              className="flex items-center gap-0.5 text-xs text-text-muted hover:text-text-primary transition-colors ml-auto"
            >
              {expanded ? <><ChevronUp size={12} /> less</> : <><ChevronDown size={12} /> more</>}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
