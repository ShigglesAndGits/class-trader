import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import LoadingState from '../components/shared/LoadingState'
import { formatDollar, formatDate, pnlColor } from '../lib/utils'

interface PositionData {
  id: number
  ticker: string
  sleeve: string
  qty: number
  entry_price: number
  cost_basis: number
  cost_per_share: number
  adjusted_cost_basis: number | null
  entry_date: string | null
  wash_sale_adjusted: boolean
}

interface TradeData {
  id: number
  ticker: string
  sleeve: string
  action: string
  confidence: number
  position_size_pct: number
  status: string
  wash_sale_flagged: boolean
  created_at: string
  resolved_at: string | null
  resolved_by: string | null
  execution: {
    qty: number
    filled_price: number
    slippage: number | null
    executed_at: string | null
  } | null
}

const ACTION_BADGE: Record<string, string> = {
  BUY: 'badge-gain',
  SELL: 'badge-loss',
  HOLD: 'badge-info',
}

const STATUS_BADGE: Record<string, string> = {
  EXECUTED: 'badge-gain',
  PENDING: 'badge-warning',
  APPROVED: 'badge-info',
  REJECTED: 'badge-loss',
  FAILED: 'badge-loss',
  SKIPPED: 'text-text-muted text-xs',
}

export default function Portfolio() {
  const { data: posData, isLoading: posLoading } = useQuery<{
    main: PositionData[]
    penny: PositionData[]
    total_count: number
  }>({
    queryKey: ['portfolio-positions'],
    queryFn: () => api.get('/api/portfolio/positions'),
    refetchInterval: 60_000,
  })

  const { data: tradeData, isLoading: tradesLoading } = useQuery<{
    trades: TradeData[]
    count: number
  }>({
    queryKey: ['portfolio-trades'],
    queryFn: () => api.get('/api/portfolio/trades'),
    refetchInterval: 120_000,
  })

  if (posLoading) return <LoadingState message="Loading portfolio..." />

  const main = posData?.main ?? []
  const penny = posData?.penny ?? []
  const trades = tradeData?.trades ?? []

  return (
    <div className="space-y-5">
      {/* Positions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <PositionList label="Main Sleeve" positions={main} />
        <PositionList label="Penny Sleeve" positions={penny} />
      </div>

      {/* Trade history */}
      <div className="card">
        <div className="card-header">Trade History ({trades.length})</div>
        {trades.length === 0 ? (
          <div className="text-text-muted text-sm py-6 text-center">No trades executed yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-muted text-xs uppercase tracking-wider">
                  <th className="text-left pb-2 pr-3">Date</th>
                  <th className="text-left pb-2 pr-3">Ticker</th>
                  <th className="text-left pb-2 pr-3">Action</th>
                  <th className="text-right pb-2 pr-3">Qty</th>
                  <th className="text-right pb-2 pr-3">Price</th>
                  <th className="text-left pb-2 pr-3">Status</th>
                  <th className="text-left pb-2">Sleeve</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {trades.map((t) => (
                  <tr key={t.id} className="hover:bg-surface-2/30">
                    <td className="py-2.5 pr-3 text-text-muted text-xs font-mono">
                      {t.execution?.executed_at
                        ? formatDate(t.execution.executed_at)
                        : formatDate(t.created_at)}
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-text-primary font-semibold">
                      {t.ticker}
                      {t.wash_sale_flagged && (
                        <span className="text-warning ml-1 text-xs" title="Wash sale">⚠</span>
                      )}
                    </td>
                    <td className="py-2.5 pr-3">
                      <span className={ACTION_BADGE[t.action]}>{t.action}</span>
                    </td>
                    <td className="py-2.5 pr-3 text-right font-mono text-text-secondary">
                      {t.execution ? t.execution.qty.toFixed(0) : '—'}
                    </td>
                    <td className="py-2.5 pr-3 text-right font-mono text-text-secondary">
                      {t.execution ? formatDollar(t.execution.filled_price) : '—'}
                    </td>
                    <td className="py-2.5 pr-3">
                      <span className={STATUS_BADGE[t.status] ?? 'text-text-muted text-xs'}>
                        {t.status}
                      </span>
                    </td>
                    <td className="py-2.5 text-xs text-text-muted font-mono">{t.sleeve}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function PositionList({ label, positions }: { label: string; positions: PositionData[] }) {
  return (
    <div className="card">
      <div className="card-header">{label}</div>
      {positions.length === 0 ? (
        <div className="text-text-muted text-sm py-4 text-center">No positions.</div>
      ) : (
        <div className="space-y-3">
          {positions.map((p) => (
            <div key={p.id} className="border-b border-border last:border-0 pb-3 last:pb-0">
              <div className="flex justify-between items-start">
                <div>
                  <span className="font-mono text-text-primary font-semibold">{p.ticker}</span>
                  {p.wash_sale_adjusted && (
                    <span className="text-warning text-xs ml-2">wash sale</span>
                  )}
                </div>
                <div className="text-right">
                  <div className="font-mono text-text-primary text-sm">{formatDollar(p.cost_basis)}</div>
                  <div className="text-text-muted text-xs">cost basis</div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 mt-1.5 text-xs text-text-muted">
                <div>
                  <div className="font-mono text-text-secondary">{p.qty.toFixed(p.qty % 1 === 0 ? 0 : 4)}</div>
                  <div>shares</div>
                </div>
                <div>
                  <div className="font-mono text-text-secondary">{formatDollar(p.entry_price)}</div>
                  <div>entry</div>
                </div>
                <div>
                  <div className="font-mono text-text-secondary">{formatDollar(p.cost_per_share)}</div>
                  <div>avg cost</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
