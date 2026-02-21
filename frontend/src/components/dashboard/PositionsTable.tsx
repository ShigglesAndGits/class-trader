import clsx from 'clsx'
import { formatDollar } from '../../lib/utils'

interface PositionRow {
  ticker: string
  sleeve: string
  qty: number
  entry_price: number
  cost_basis: number
  entry_date: string | null
}

interface PositionsTableProps {
  positions: PositionRow[]
}

export default function PositionsTable({ positions }: PositionsTableProps) {
  if (positions.length === 0) {
    return (
      <div className="text-text-muted text-sm py-6 text-center">
        No open positions. The market can wait.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-text-muted text-xs uppercase tracking-wider">
            <th className="text-left pb-2 pr-4">Ticker</th>
            <th className="text-left pb-2 pr-4">Sleeve</th>
            <th className="text-right pb-2 pr-4">Qty</th>
            <th className="text-right pb-2 pr-4">Entry</th>
            <th className="text-right pb-2">Cost Basis</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {positions.map((p) => (
            <tr key={`${p.ticker}-${p.sleeve}`} className="hover:bg-surface-2/30">
              <td className="py-2.5 pr-4 font-mono text-text-primary font-semibold">
                {p.ticker}
              </td>
              <td className="py-2.5 pr-4">
                <span
                  className={clsx(
                    'text-xs px-1.5 py-0.5 rounded font-mono',
                    p.sleeve === 'MAIN'
                      ? 'text-info bg-info/10'
                      : 'text-warning bg-warning/10'
                  )}
                >
                  {p.sleeve}
                </span>
              </td>
              <td className="py-2.5 pr-4 text-right font-mono text-text-secondary">
                {p.qty.toFixed(p.qty % 1 === 0 ? 0 : 4)}
              </td>
              <td className="py-2.5 pr-4 text-right font-mono text-text-secondary">
                {formatDollar(p.entry_price)}
              </td>
              <td className="py-2.5 text-right font-mono text-text-primary">
                {formatDollar(p.cost_basis)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
