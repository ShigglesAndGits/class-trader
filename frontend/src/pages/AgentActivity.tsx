import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import LoadingState from '../components/shared/LoadingState'
import AgentCard from '../components/agents/AgentCard'
import { formatDate, formatTime } from '../lib/utils'
import type { AgentInteraction, PipelineRun, Regime } from '../lib/types'

interface RunsResponse {
  runs: Array<PipelineRun & { regime: Regime | null; regime_confidence: number | null }>
}

interface RunDetailResponse {
  run: PipelineRun
  interactions: AgentInteraction[]
}

const STATUS_COLOR: Record<string, string> = {
  RUNNING: 'text-warning',
  COMPLETED: 'text-gain',
  FAILED: 'text-loss',
  PAUSED: 'text-text-muted',
}

export default function AgentActivity() {
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)

  const { data: runsData, isLoading: runsLoading } = useQuery<RunsResponse>({
    queryKey: ['agent-runs'],
    queryFn: () => api.get('/api/agents/runs'),
    refetchInterval: 30_000,
  })

  const { data: runDetail, isLoading: detailLoading } = useQuery<RunDetailResponse>({
    queryKey: ['agent-run', selectedRunId],
    queryFn: () => api.get(`/api/agents/runs/${selectedRunId}`),
    enabled: selectedRunId !== null,
  })

  const runs = runsData?.runs ?? []

  if (runsLoading) return <LoadingState message="Loading pipeline history..." />

  return (
    <div className="flex gap-5 h-full">
      {/* Run list */}
      <div className="w-72 shrink-0 space-y-2">
        <div className="card-header px-0">Pipeline Runs</div>
        {runs.length === 0 ? (
          <div className="card text-center py-8">
            <div className="text-text-muted text-sm">No pipeline runs yet. Agents are standing by.</div>
          </div>
        ) : (
          <div className="space-y-1.5">
            {runs.map((run) => (
              <button
                key={run.id}
                onClick={() => setSelectedRunId(run.id)}
                className={clsx(
                  'w-full text-left p-3 rounded-lg border transition-colors',
                  selectedRunId === run.id
                    ? 'bg-surface-2 border-border'
                    : 'bg-surface border-border hover:border-border hover:bg-surface-2/50'
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-text-secondary text-xs font-mono">#{run.id}</span>
                  <span className={clsx('text-xs font-mono', STATUS_COLOR[run.status])}>
                    {run.status}
                  </span>
                </div>
                <div className="text-text-primary text-sm font-medium">{run.run_type}</div>
                <div className="text-text-muted text-xs mt-0.5 font-mono">
                  {formatDate(run.started_at)} · {formatTime(run.started_at)}
                </div>
                {run.regime && (
                  <div className="text-text-muted text-xs mt-1 font-mono">
                    {run.regime}
                    {run.regime_confidence && ` · ${Math.round(run.regime_confidence * 100)}%`}
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Run detail */}
      <div className="flex-1 min-w-0">
        {!selectedRunId ? (
          <div className="card h-full flex items-center justify-center text-text-muted text-sm">
            Select a pipeline run to view agent reasoning.
          </div>
        ) : detailLoading ? (
          <LoadingState message="Loading agent interactions..." />
        ) : runDetail ? (
          <div className="space-y-3">
            <div className="card">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-text-primary font-medium">Run #{runDetail.run.id}</span>
                  <span className="text-text-muted text-xs ml-2 font-mono">{runDetail.run.run_type}</span>
                </div>
                <span className={clsx('text-sm font-mono', STATUS_COLOR[runDetail.run.status])}>
                  {runDetail.run.status}
                </span>
              </div>
              <div className="text-text-muted text-xs mt-1 font-mono">
                Started {formatDate(runDetail.run.started_at)} at {formatTime(runDetail.run.started_at)}
                {runDetail.run.completed_at &&
                  ` · completed at ${formatTime(runDetail.run.completed_at)}`}
              </div>
            </div>

            {runDetail.interactions.length === 0 ? (
              <div className="card text-center py-8 text-text-muted text-sm">
                No agent interactions logged for this run.
              </div>
            ) : (
              runDetail.interactions.map((interaction) => (
                <AgentCard key={interaction.id} interaction={interaction} />
              ))
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}
