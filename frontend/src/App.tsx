import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { useWebSocket } from './hooks/useWebSocket'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import AgentActivity from './pages/AgentActivity'
import Portfolio from './pages/Portfolio'
import Approvals from './pages/Approvals'
import NewsSentiment from './pages/NewsSentiment'
import Analytics from './pages/Analytics'
import Settings from './pages/Settings'
import Discovery from './pages/Discovery'

/**
 * Maps backend WebSocket event types to TanStack Query cache keys to invalidate.
 * When the backend broadcasts an event, the affected pages refresh immediately
 * instead of waiting for the next polling interval.
 *
 * Event types emitted by the backend:
 *   trade_executed    — execution engine, order filled
 *   trade_failed      — execution engine, order timed out / cancelled
 *   pipeline_started  — pipeline.py, run began
 *   pipeline_complete — pipeline.py, run finished
 *   circuit_breaker   — risk_manager, breaker triggered
 *   retail_spike      — scheduler, TendieBot velocity alert
 */
const WS_INVALIDATIONS: Record<string, string[][]> = {
  trade_executed: [
    ['dashboard'],
    ['portfolio-positions'],
    ['portfolio-trades'],
    ['approvals'],
  ],
  trade_failed: [['dashboard'], ['approvals']],
  trade_approved: [['approvals'], ['dashboard']],
  trade_rejected: [['approvals'], ['dashboard']],
  pipeline_started: [['agent-runs'], ['dashboard']],
  pipeline_complete: [
    ['agent-runs'],
    ['dashboard'],
    ['analytics-equity-curve'],
    ['analytics-performance'],
  ],
  circuit_breaker: [['circuit-breakers'], ['dashboard']],
  retail_spike: [['news-retail']],
}

export default function App() {
  const queryClient = useQueryClient()

  // Stable reference — queryClient never changes identity within a session.
  const handleMessage = useCallback(
    (data: Record<string, unknown>) => {
      const keys = WS_INVALIDATIONS[data.type as string]
      if (keys) {
        for (const key of keys) {
          queryClient.invalidateQueries({ queryKey: key })
        }
      }
    },
    [queryClient],
  )

  // Single persistent WebSocket connection for the whole app.
  useWebSocket(handleMessage)

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="agents" element={<AgentActivity />} />
          <Route path="portfolio" element={<Portfolio />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="news" element={<NewsSentiment />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="settings" element={<Settings />} />
          <Route path="discover" element={<Discovery />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
