import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from 'recharts'
import { api } from '../api/client'
import LoadingState from '../components/shared/LoadingState'
import { formatDollar, formatDate } from '../lib/utils'

interface PerformanceMetrics {
  trade_count: number
  win_count: number
  loss_count: number
  win_rate: number | null
  avg_gain: number | null
  avg_loss: number | null
  total_realized_pnl: number
  largest_gain: number | null
  largest_loss: number | null
  sharpe_ratio: number | null
}

interface EquityPoint {
  timestamp: string
  total_equity: number
  spy_benchmark_value: number | null
  daily_pnl: number | null
}

export default function Analytics() {
  const { data: perfData, isLoading: perfLoading } = useQuery<{ metrics: PerformanceMetrics }>({
    queryKey: ['analytics-performance'],
    queryFn: () => api.get('/api/analytics/performance'),
    refetchInterval: 300_000,
  })

  const { data: curveData, isLoading: curveLoading } = useQuery<{ data: EquityPoint[]; has_benchmark: boolean }>({
    queryKey: ['analytics-equity-curve'],
    queryFn: () => api.get('/api/analytics/equity-curve'),
    refetchInterval: 300_000,
  })

  if (perfLoading || curveLoading) return <LoadingState message="Loading analytics..." />

  const metrics = perfData?.metrics
  const curve = curveData?.data ?? []
  const hasBenchmark = curveData?.has_benchmark

  const metricCards = [
    {
      label: 'Win Rate',
      value: metrics?.win_rate != null ? `${(metrics.win_rate * 100).toFixed(1)}%` : '—',
      sub: metrics?.trade_count ? `${metrics.win_count}W / ${metrics.loss_count}L` : null,
    },
    {
      label: 'Avg Gain',
      value: metrics?.avg_gain != null ? formatDollar(metrics.avg_gain, true) : '—',
      positive: true,
    },
    {
      label: 'Avg Loss',
      value: metrics?.avg_loss != null ? formatDollar(metrics.avg_loss) : '—',
      positive: false,
    },
    {
      label: 'Realized P&L',
      value: metrics ? formatDollar(metrics.total_realized_pnl, true) : '—',
      positive: (metrics?.total_realized_pnl ?? 0) >= 0,
    },
    {
      label: 'Largest Win',
      value: metrics?.largest_gain != null ? formatDollar(metrics.largest_gain, true) : '—',
    },
    {
      label: 'Sharpe Ratio',
      value: metrics?.sharpe_ratio != null ? metrics.sharpe_ratio.toFixed(2) : '—',
      sub: metrics?.trade_count && metrics.trade_count < 5 ? 'Need 5+ trades' : null,
    },
  ]

  return (
    <div className="space-y-5">
      {/* Metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {metricCards.map(({ label, value, sub, positive }) => (
          <div key={label} className="card">
            <div className="card-header mb-1">{label}</div>
            <div
              className={
                positive === true ? 'text-gain font-mono text-lg' :
                positive === false ? 'text-loss font-mono text-lg' :
                'text-text-primary font-mono text-lg'
              }
            >
              {value}
            </div>
            {sub && <div className="text-text-muted text-xs mt-0.5">{sub}</div>}
          </div>
        ))}
      </div>

      {/* Equity curve */}
      <div className="card">
        <div className="card-header">
          Equity Curve
          {hasBenchmark && <span className="ml-2 text-text-muted font-normal normal-case">vs SPY</span>}
        </div>

        {curve.length < 2 ? (
          <div className="text-text-muted text-sm py-8 text-center">
            History begins when the first trade executes.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={curve} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10B981" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="spyGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.1} />
                  <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2d44" vertical={false} />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(v) => formatDate(v)}
                tick={{ fill: '#6B7280', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v) => `$${v.toFixed(0)}`}
                tick={{ fill: '#6B7280', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                width={55}
              />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #1f2d44', borderRadius: 6 }}
                labelStyle={{ color: '#9CA3AF', fontSize: 11 }}
                formatter={(value: number, name: string) => [
                  formatDollar(value),
                  name === 'total_equity' ? 'Portfolio' : 'SPY',
                ]}
                labelFormatter={(label) => formatDate(label)}
              />
              <Area
                type="monotone"
                dataKey="total_equity"
                stroke="#10B981"
                strokeWidth={2}
                fill="url(#equityGradient)"
                dot={false}
                isAnimationActive={false}
              />
              {hasBenchmark && (
                <Area
                  type="monotone"
                  dataKey="spy_benchmark_value"
                  stroke="#3B82F6"
                  strokeWidth={1.5}
                  fill="url(#spyGradient)"
                  strokeDasharray="4 4"
                  dot={false}
                  isAnimationActive={false}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
