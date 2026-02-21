import clsx from 'clsx'
import { formatDollar, formatPct } from '../../lib/utils'

interface PriceChangeProps {
  value: number
  pct?: number
  size?: 'sm' | 'md' | 'lg'
  showSign?: boolean
}

export default function PriceChange({ value, pct, size = 'md', showSign = true }: PriceChangeProps) {
  const isPositive = value >= 0
  const colorClass = isPositive ? 'text-gain' : 'text-loss'

  const sizeClasses = {
    sm: 'text-xs font-mono',
    md: 'text-sm font-mono',
    lg: 'text-base font-mono font-semibold',
  }

  return (
    <span className={clsx(colorClass, sizeClasses[size])}>
      {formatDollar(value, showSign)}
      {pct !== undefined && (
        <span className="ml-1.5 opacity-75">({formatPct(pct)})</span>
      )}
    </span>
  )
}
