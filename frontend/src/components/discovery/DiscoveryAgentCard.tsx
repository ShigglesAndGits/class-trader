import { useState } from 'react'
import { ChevronDown, ChevronUp, CheckCircle2, Loader2, Clock } from 'lucide-react'
import clsx from 'clsx'
import { DISCOVERY_AGENT_LABELS, EXPLORER_TOOL_LABELS } from '../../lib/constants'
import type { AgentStep } from '../../lib/types'

interface RegimeData {
  regime: string
  confidence: number
  reasoning: string
  key_indicators: string[]
}

interface AnalysisData {
  ticker: string
  stance: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  confidence: number
  reasoning: string
  key_data_points: string[]
}

interface VerdictData {
  ticker: string
  bull_bear_agreement: string
  confidence: number
  reasoning: string
  flagged_issues: string[]
  thesis_drift_warning: boolean
}

interface DiscoveryRec {
  ticker: string
  action: string
  confidence: number
  reasoning: string
}

interface DiscoveryRecGroup {
  recommendations: DiscoveryRec[]
  overall_thesis: string
  caveats: string[]
}

interface Props {
  step: AgentStep
  isRunning: boolean
}

function stanceColor(stance: string) {
  if (stance === 'BULLISH') return 'text-gain'
  if (stance === 'BEARISH') return 'text-loss'
  return 'text-text-secondary'
}

function agreementLabel(ag: string) {
  if (ag === 'AGREE_BULLISH') return { label: 'Agreed Bullish', color: 'text-gain' }
  if (ag === 'AGREE_BEARISH') return { label: 'Agreed Bearish', color: 'text-loss' }
  if (ag === 'DISAGREE') return { label: 'Disagreed', color: 'text-warning' }
  return { label: 'Insufficient Data', color: 'text-text-muted' }
}

export default function DiscoveryAgentCard({ step, isRunning }: Props) {
  const [expanded, setExpanded] = useState(false)
  const label = DISCOVERY_AGENT_LABELS[step.agent] ?? step.agent

  const isComplete = step.status === 'complete'
  const isPending = step.status === 'pending' && !isRunning

  return (
    <div
      className={clsx(
        'card transition-all duration-300',
        isPending && 'opacity-40',
        isRunning && 'ring-1 ring-info/40',
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          {isComplete ? (
            <CheckCircle2 size={15} className="text-gain shrink-0" />
          ) : isRunning ? (
            <Loader2 size={15} className="text-info shrink-0 animate-spin" />
          ) : (
            <Clock size={15} className="text-text-muted shrink-0" />
          )}
          <span className={clsx('text-sm font-medium', isPending ? 'text-text-muted' : 'text-text-primary')}>
            {label}
          </span>
        </div>

        {isComplete && (
          <button
            onClick={() => setExpanded(e => !e)}
            className="text-text-muted hover:text-text-primary transition-colors"
            aria-label={expanded ? 'Collapse' : 'Expand'}
          >
            {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          </button>
        )}

        {isRunning && (
          <span className="text-xs text-info/70 animate-pulse">
            {step.agent === 'EXPLORER' ? 'exploring…' : 'analyzing…'}
          </span>
        )}
        {isPending && (
          <span className="text-xs text-text-muted">waiting</span>
        )}
      </div>

      {/* Explorer tool calls (live, while running or after complete) */}
      {step.agent === 'EXPLORER' && (isRunning || isComplete) && !!step.data?.toolCalls && (
        <div className="mt-2 space-y-1">
          {(step.data.toolCalls as Array<{ tool: string; input: Record<string, unknown> }>).map(
            (tc, i) => (
              <div key={i} className="flex items-center gap-1.5 text-xs text-text-muted">
                <Loader2
                  size={10}
                  className={isComplete ? 'hidden' : 'text-info animate-spin shrink-0'}
                />
                <CheckCircle2
                  size={10}
                  className={isComplete ? 'text-gain shrink-0' : 'hidden'}
                />
                <span>
                  {EXPLORER_TOOL_LABELS[tc.tool] ?? tc.tool}
                  {tc.tool === 'lookup_ticker' && !!tc.input?.ticker && (
                    <span className="font-mono ml-1">{String(tc.input.ticker)}</span>
                  )}
                  {tc.tool === 'search_financial_news' && !!tc.input?.query && (
                    <span className="ml-1 italic">"{String(tc.input.query)}"</span>
                  )}
                </span>
              </div>
            ),
          )}
        </div>
      )}

      {/* Summary (always visible when complete) */}
      {isComplete && step.data && (
        <div className="mt-2">
          <AgentSummary agent={step.agent} data={step.data} />
        </div>
      )}

      {/* Expanded detail */}
      {isComplete && expanded && step.data && (
        <div className="mt-3 pt-3 border-t border-border">
          <AgentDetail agent={step.agent} data={step.data} />
        </div>
      )}
    </div>
  )
}

function AgentSummary({ agent, data }: { agent: string; data: Record<string, unknown> }) {
  if (agent === 'EXPLORER') {
    const tickers = data.tickers as string[] | undefined
    if (!tickers?.length) return null
    return (
      <p className="text-xs text-text-secondary">
        Found{' '}
        <span className="font-mono text-text-primary">{tickers.join(', ')}</span>
      </p>
    )
  }

  if (agent === 'REGIME_ANALYST') {
    const r = data.regime as RegimeData | undefined
    if (!r) return null
    return (
      <p className="text-xs text-text-secondary">
        <span className="text-text-primary font-medium">{r.regime.replace('_', ' ')}</span>
        {' '}— confidence {(r.confidence * 100).toFixed(0)}%
      </p>
    )
  }

  if (agent === 'BULL' || agent === 'BEAR') {
    const analyses = data.analyses as AnalysisData[] | undefined
    if (!analyses?.length) return null
    const bullish = analyses.filter(a => a.stance === 'BULLISH').length
    const bearish = analyses.filter(a => a.stance === 'BEARISH').length
    return (
      <p className="text-xs text-text-secondary">
        {analyses.length} tickers — {' '}
        <span className="text-gain">{bullish} bullish</span>
        {', '}
        <span className="text-loss">{bearish} bearish</span>
        {analyses.length - bullish - bearish > 0 && `, ${analyses.length - bullish - bearish} neutral`}
      </p>
    )
  }

  if (agent === 'RESEARCHER') {
    const verdicts = data.verdicts as VerdictData[] | undefined
    if (!verdicts?.length) return null
    const drifts = verdicts.filter(v => v.thesis_drift_warning).length
    return (
      <p className="text-xs text-text-secondary">
        {verdicts.length} verdicts
        {drifts > 0 && <span className="text-warning ml-1">· {drifts} drift warning{drifts > 1 ? 's' : ''}</span>}
      </p>
    )
  }

  if (agent === 'DISCOVERY_PM') {
    const recs = data.recommendations as DiscoveryRecGroup | undefined
    if (!recs) return null
    const buys = recs.recommendations.filter(r => r.action === 'BUY').length
    const considers = recs.recommendations.filter(r => r.action === 'CONSIDER').length
    return (
      <p className="text-xs text-text-secondary">
        <span className="text-gain">{buys} BUY</span>
        {considers > 0 && <span className="text-warning ml-1">· {considers} CONSIDER</span>}
        {recs.recommendations.length - buys - considers > 0 && (
          <span className="text-loss ml-1">
            · {recs.recommendations.length - buys - considers} AVOID
          </span>
        )}
      </p>
    )
  }

  return null
}

function AgentDetail({ agent, data }: { agent: string; data: Record<string, unknown> }) {
  if (agent === 'EXPLORER') {
    const reasoning = data.reasoning as string | undefined
    if (!reasoning) return null
    return <p className="text-xs text-text-secondary leading-relaxed">{reasoning}</p>
  }

  if (agent === 'REGIME_ANALYST') {
    const r = data.regime as RegimeData | undefined
    if (!r) return null
    return (
      <div className="space-y-2">
        <p className="text-xs text-text-secondary leading-relaxed">{r.reasoning}</p>
        {r.key_indicators.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {r.key_indicators.map((ind, i) => (
              <span key={i} className="badge badge-info text-xs">{ind}</span>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (agent === 'BULL' || agent === 'BEAR') {
    const analyses = data.analyses as AnalysisData[] | undefined
    if (!analyses?.length) return null
    return (
      <div className="space-y-3">
        {analyses.map(a => (
          <div key={a.ticker}>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-xs font-medium text-text-primary">{a.ticker}</span>
              <span className={clsx('text-xs font-medium', stanceColor(a.stance))}>{a.stance}</span>
              <span className="text-xs text-text-muted">{(a.confidence * 100).toFixed(0)}%</span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed">{a.reasoning}</p>
          </div>
        ))}
      </div>
    )
  }

  if (agent === 'RESEARCHER') {
    const verdicts = data.verdicts as VerdictData[] | undefined
    if (!verdicts?.length) return null
    return (
      <div className="space-y-3">
        {verdicts.map(v => {
          const ag = agreementLabel(v.bull_bear_agreement)
          return (
            <div key={v.ticker}>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs font-medium text-text-primary">{v.ticker}</span>
                <span className={clsx('text-xs', ag.color)}>{ag.label}</span>
                {v.thesis_drift_warning && (
                  <span className="badge badge-warning text-xs">drift</span>
                )}
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">{v.reasoning}</p>
              {v.flagged_issues.length > 0 && (
                <ul className="mt-1 space-y-0.5">
                  {v.flagged_issues.map((issue, i) => (
                    <li key={i} className="text-xs text-warning">⚑ {issue}</li>
                  ))}
                </ul>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  if (agent === 'DISCOVERY_PM') {
    const recs = data.recommendations as DiscoveryRecGroup | undefined
    if (!recs) return null
    return (
      <div className="space-y-3">
        <p className="text-xs text-text-secondary italic leading-relaxed">{recs.overall_thesis}</p>
        {recs.caveats.length > 0 && (
          <ul className="space-y-0.5">
            {recs.caveats.map((c, i) => (
              <li key={i} className="text-xs text-text-muted">· {c}</li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  return null
}
