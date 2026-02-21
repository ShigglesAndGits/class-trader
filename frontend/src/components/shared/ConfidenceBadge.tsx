import clsx from 'clsx'
import { formatConfidence } from '../../lib/utils'

interface ConfidenceBadgeProps {
  value: number  // 0.0 – 1.0
}

export default function ConfidenceBadge({ value }: ConfidenceBadgeProps) {
  const cls =
    value >= 0.80 ? 'badge-gain' :
    value >= 0.65 ? 'badge-warning' :
    'badge-loss'

  return <span className={clsx(cls)}>{formatConfidence(value)}</span>
}
