import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CheckSquare, Play } from 'lucide-react'
import { api } from '../api/client'
import LoadingState from '../components/shared/LoadingState'
import RegimeBadge from '../components/dashboard/RegimeBadge'
import PositionsTable from '../components/dashboard/PositionsTable'
import RecentActivity from '../components/dashboard/RecentActivity'
import AutoApproveToggle from '../components/dashboard/AutoApproveToggle'
import NextRunCountdown from '../components/dashboard/NextRunCountdown'
import PriceChange from '../components/shared/PriceChange'
import { formatDollar } from '../lib/utils'
import type { Regime } from '../lib/types'

interface DashboardData {
  portfolio: {
    total_equity: number
    main_equity: number
    penny_equity: number
    cash_balance: number
    daily_pnl: number | null
    daily_pnl_pct: number | null
    source: string
  }
  regime: {
    regime: Regime
    confidence: number
    run_id: number
    run_type: string
    timestamp: string
  } | null
  positions: Array<{
    ticker: string
    sleeve: string
    qty: number
    entry_price: number
    cost_basis: number
    entry_date: string | null
  }>
  recent_decisions: Array<{
    id: number
    ticker: string
    sleeve: string
    action: string
    confidence: number
    status: string
    wash_sale_flagged: boolean
    created_at: string
    resolved_by: string | null
  }>
  last_run: { id: number; status: string; started_at: string } | null
  auto_approve: boolean
  pending_approvals: number
}

export default function Dashboard() {
  const client = useQueryClient()

  const { data, isLoading } = useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: () => api.get('/api/dashboard/summary'),
    refetchInterval: 60_000,
  })

  const triggerRun = useMutation({
    mutationFn: () => api.post('/api/agents/trigger', { run_type: 'MANUAL' }),
    onSuccess: () => {
      setTimeout(() => client.invalidateQueries({ queryKey: ['dashboard'] }), 3000)
    },
  })

  if (isLoading) return <LoadingState message="Loading dashboard..." />

  const portfolio = data?.portfolio
  const regime = data?.regime

  return (
    <div className="space-y-5">
      {/* Top row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        <div className="card">
          <div className="card-header">Portfolio Value</div>
          <div className="text-3xl font-mono text-text-primary mb-1">
            {portfolio ? formatDollar(portfolio.total_equity) : '—'}
          </div>
          {portfolio?.daily_pnl != null ? (
            <PriceChange
              value={portfolio.daily_pnl}
              pct={portfolio.daily_pnl_pct ?? undefined}
              size="sm"
              showSign
            />
          ) : (
            <span className="text-text-muted text-xs">
              {portfolio?.source === 'estimated' ? 'Estimated from config · no trades yet' : 'No data'}
            </span>
          )}
          {portfolio && (
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-text-muted border-t border-border pt-3">
              <div>
                <div className="text-text-secondary font-mono text-sm">{formatDollar(portfolio.main_equity)}</div>
                <div>Main sleeve</div>
              </div>
              <div>
                <div className="text-text-secondary font-mono text-sm">{formatDollar(portfolio.penny_equity)}</div>
                <div>Penny sleeve</div>
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-header">Market Regime</div>
          {regime ? (
            <div className="space-y-2">
              <RegimeBadge regime={regime.regime} confidence={regime.confidence} />
              <div className="text-text-muted text-xs">
                {regime.run_type} · {new Date(regime.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          ) : (
            <div className="text-text-muted text-sm">Awaiting first pipeline run.</div>
          )}
        </div>

        <div className="card flex flex-col gap-4">
          <AutoApproveToggle enabled={data?.auto_approve ?? false} />
          <NextRunCountdown />
          <div className="flex items-center gap-3 border-t border-border pt-3">
            <button
              onClick={() => triggerRun.mutate()}
              disabled={triggerRun.isPending}
              className="btn-primary flex items-center gap-1.5 text-xs py-1.5 disabled:opacity-50"
            >
              <Play size={12} />
              {triggerRun.isPending ? 'Triggering…' : 'Run Pipeline'}
            </button>
            {(data?.pending_approvals ?? 0) > 0 && (
              <Link
                to="/approvals"
                className="flex items-center gap-1.5 text-warning text-xs font-mono hover:underline"
              >
                <CheckSquare size={12} />
                {data!.pending_approvals} pending
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card">
          <div className="card-header">
            Open Positions ({data?.positions.length ?? 0})
          </div>
          <PositionsTable positions={data?.positions ?? []} />
        </div>
        <div className="card">
          <div className="card-header">Recent Decisions (24h)</div>
          <RecentActivity decisions={data?.recent_decisions ?? []} />
        </div>
      </div>
    </div>
  )
}
