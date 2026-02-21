import clsx from 'clsx'
import { REGIME_LABELS } from '../../lib/constants'
import type { Regime } from '../../lib/types'

interface RegimeBadgeProps {
  regime: Regime
  confidence: number
}

const REGIME_BG: Record<Regime, string> = {
  TRENDING_UP: 'border-gain/40 bg-gain/10 text-gain',
  TRENDING_DOWN: 'border-loss/40 bg-loss/10 text-loss',
  RANGING: 'border-warning/40 bg-warning/10 text-warning',
  HIGH_VOLATILITY: 'border-loss/40 bg-loss/10 text-loss',
}

export default function RegimeBadge({ regime, confidence }: RegimeBadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-2 px-3 py-1.5 rounded-md border text-sm font-mono',
        REGIME_BG[regime]
      )}
    >
      <span>{REGIME_LABELS[regime] ?? regime}</span>
      <span className="opacity-60 text-xs">{Math.round(confidence * 100)}%</span>
    </span>
  )
}
