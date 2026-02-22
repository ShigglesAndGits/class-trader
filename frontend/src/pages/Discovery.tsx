/**
 * Stock Discovery Chat
 *
 * Type a query, watch agents debate in real time, then push
 * recommendations to the approval queue or watchlist.
 */

import { useState } from 'react'
import { History, X } from 'lucide-react'
import { api } from '../api/client'
import { useDiscoveryStream } from '../hooks/useDiscoveryStream'
import QueryInput from '../components/discovery/QueryInput'
import DiscoveryAgentTimeline from '../components/discovery/DiscoveryAgentTimeline'
import RecommendationsList from '../components/discovery/RecommendationsList'
import DiscoveryChat from '../components/discovery/DiscoveryChat'
import type { DiscoveryChatMessage, QueryMode } from '../lib/types'

interface StartResponse {
  session_id: number
  tickers: string[]
  status: string
}

export default function Discovery() {
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [tickers, setTickers] = useState<string[]>([])
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [chatMessages, setChatMessages] = useState<DiscoveryChatMessage[]>([])

  const stream = useDiscoveryStream()

  async function handleQuery(query: string, mode: QueryMode) {
    setStartError(null)
    setStarting(true)
    stream.reset()
    setChatMessages([])
    setTickers([])
    setSessionId(null)

    try {
      const data = await api.post<StartResponse>('/api/discovery/sessions', {
        query,
        query_mode: mode,
        sleeve_hint: 'MAIN',
      })
      setSessionId(data.session_id)
      setTickers(data.tickers)
      stream.startStream(data.session_id, mode === 'EXPLORE')
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to start session.'
      setStartError(msg.replace(/^API \d+: /, ''))
    } finally {
      setStarting(false)
    }
  }

  function handleRebate(newSessionId: number) {
    // Switch to a new session's stream for the re-debate
    setSessionId(newSessionId)
    stream.startStream(newSessionId)
    setChatMessages([])
  }

  function handleReset() {
    stream.reset()
    setSessionId(null)
    setTickers([])
    setStartError(null)
    setChatMessages([])
  }

  const hasSession = sessionId !== null
  const showTimeline = hasSession || stream.isStreaming
  const showRecommendations = stream.recommendations !== null
  const showChat = showRecommendations && sessionId !== null
  const confirmedTickers = stream.confirmedTickers.length > 0 ? stream.confirmedTickers : tickers

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Discover</h1>
          <p className="text-sm text-text-muted mt-0.5">
            Research stocks. The agents will argue about it.
          </p>
        </div>
        {hasSession && (
          <button
            onClick={handleReset}
            className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary transition-colors"
          >
            <X size={13} />
            New search
          </button>
        )}
      </div>

      {/* Query input */}
      <div className="card">
        <QueryInput
          onSubmit={handleQuery}
          isLoading={starting}
          disabled={stream.isStreaming}
        />

        {startError && (
          <p className="mt-2 text-xs text-loss">{startError}</p>
        )}
      </div>

      {/* Session status bar */}
      {hasSession && confirmedTickers.length > 0 && (
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <History size={12} />
          <span>
            Session #{sessionId} — analyzing{' '}
            <span className="font-mono text-text-secondary">{confirmedTickers.join(', ')}</span>
          </span>
        </div>
      )}

      {/* Agent timeline */}
      {showTimeline && (
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wide font-medium mb-2">Agent Pipeline</p>
          <DiscoveryAgentTimeline
            steps={stream.steps}
            currentAgent={stream.currentAgent}
          />
        </div>
      )}

      {/* Pipeline error */}
      {stream.error && (
        <div className="card border-loss/30 bg-loss/5">
          <p className="text-sm text-loss">{stream.error}</p>
          <p className="text-xs text-text-muted mt-1">
            The pipeline hit an unrecoverable error. Start a new search.
          </p>
        </div>
      )}

      {/* Recommendations */}
      {showRecommendations && sessionId !== null && (
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wide font-medium mb-2">Recommendations</p>
          <RecommendationsList
            sessionId={sessionId}
            recommendations={stream.recommendations!}
          />
        </div>
      )}

      {/* Chat */}
      {showChat && sessionId !== null && (
        <DiscoveryChat
          sessionId={sessionId}
          messages={chatMessages}
          onNewMessages={setChatMessages}
          onRebate={handleRebate}
        />
      )}
    </div>
  )
}
