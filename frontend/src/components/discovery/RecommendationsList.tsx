import { useState } from 'react'
import { Send, BookmarkPlus } from 'lucide-react'
import clsx from 'clsx'
import RecommendationCard from './RecommendationCard'
import type { DiscoveryRecommendations, Sleeve } from '../../lib/types'

interface Props {
  sessionId: number
  recommendations: DiscoveryRecommendations
  onPushedToApprovals?: (count: number) => void
  onPushedToWatchlist?: (count: number) => void
}

export default function RecommendationsList({
  sessionId,
  recommendations,
  onPushedToApprovals,
  onPushedToWatchlist,
}: Props) {
  const { recommendations: recs, overall_thesis, caveats } = recommendations
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [sleeve, setSleeve] = useState<Sleeve>('MAIN')
  const [pushingApprovals, setPushingApprovals] = useState(false)
  const [pushingWatchlist, setPushingWatchlist] = useState(false)
  const [approvalsMsg, setApprovalsMsg] = useState<string | null>(null)
  const [watchlistMsg, setWatchlistMsg] = useState<string | null>(null)

  function toggle(index: number) {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  async function pushToApprovals() {
    // Only BUY / CONSIDER can be pushed to the approval queue — not AVOID
    const approvableIndices = Array.from(selected).filter(i => recs[i]?.action !== 'AVOID')
    if (approvableIndices.length === 0) return
    setPushingApprovals(true)
    setApprovalsMsg(null)
    try {
      const res = await fetch(`/api/discovery/sessions/${sessionId}/push-to-approvals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recommendation_indices: approvableIndices,
          sleeve,
        }),
      })
      const data = (await res.json()) as { queued: number }
      setApprovalsMsg(`${data.queued} trade${data.queued !== 1 ? 's' : ''} queued for approval.`)
      onPushedToApprovals?.(data.queued)
      setSelected(new Set())
    } catch {
      setApprovalsMsg('Failed to push to approvals.')
    } finally {
      setPushingApprovals(false)
    }
  }

  async function pushToWatchlist() {
    const tickers = Array.from(selected)
      .map(i => recs[i]?.ticker)
      .filter(Boolean) as string[]
    if (tickers.length === 0) return
    setPushingWatchlist(true)
    setWatchlistMsg(null)
    try {
      const res = await fetch(`/api/discovery/sessions/${sessionId}/push-to-watchlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers, sleeve }),
      })
      const data = (await res.json()) as { added: number; already_existed: number }
      setWatchlistMsg(
        `${data.added} added${data.already_existed > 0 ? `, ${data.already_existed} already on watchlist` : ''}.`,
      )
      onPushedToWatchlist?.(data.added)
      setSelected(new Set())
    } catch {
      setWatchlistMsg('Failed to update watchlist.')
    } finally {
      setPushingWatchlist(false)
    }
  }

  const selectedApprovable = Array.from(selected).filter(i => recs[i]?.action !== 'AVOID').length

  return (
    <div className="space-y-4">
      {/* Thesis */}
      <div className="card">
        <p className="text-xs text-text-muted uppercase tracking-wide font-medium mb-1">Thesis</p>
        <p className="text-sm text-text-secondary leading-relaxed">{overall_thesis}</p>
        {caveats.length > 0 && (
          <ul className="mt-2 space-y-0.5">
            {caveats.map((c, i) => (
              <li key={i} className="text-xs text-warning">⚑ {c}</li>
            ))}
          </ul>
        )}
      </div>

      {/* Recommendation cards */}
      <div className="space-y-2">
        {recs.map((rec, i) => (
          <RecommendationCard
            key={rec.ticker}
            rec={rec}
            index={i}
            selected={selected.has(i)}
            onToggle={toggle}
          />
        ))}
      </div>

      {/* Actions */}
      {recs.length > 0 && (
        <div className="card">
          <div className="flex flex-wrap items-center gap-3">
            {/* Sleeve selector */}
            <div className="flex gap-1 bg-surface-2 rounded-md p-0.5 border border-border">
              {(['MAIN', 'PENNY'] as Sleeve[]).map(s => (
                <button
                  key={s}
                  onClick={() => setSleeve(s)}
                  className={clsx(
                    'px-3 py-1 text-xs rounded transition-colors',
                    sleeve === s
                      ? 'bg-surface-2 text-text-primary'
                      : 'text-text-muted hover:text-text-primary',
                  )}
                >
                  {s}
                </button>
              ))}
            </div>

            <span className="text-xs text-text-muted">
              {selected.size === 0
                ? 'Select recommendations above'
                : `${selected.size} selected${selectedApprovable < selected.size ? ` · ${selected.size - selectedApprovable} AVOID (watchlist only)` : ''}`}
            </span>

            <div className="flex gap-2 ml-auto">
              <button
                onClick={pushToWatchlist}
                disabled={selected.size === 0 || pushingWatchlist}
                className="flex items-center gap-1.5 btn-ghost text-sm disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <BookmarkPlus size={14} />
                Watchlist
              </button>
              <button
                onClick={pushToApprovals}
                disabled={selectedApprovable === 0 || pushingApprovals}
                className="flex items-center gap-1.5 btn-primary text-sm disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Send size={14} />
                Push to Approvals
              </button>
            </div>
          </div>

          {(approvalsMsg || watchlistMsg) && (
            <p className="text-xs text-gain mt-2">{approvalsMsg || watchlistMsg}</p>
          )}
        </div>
      )}
    </div>
  )
}
