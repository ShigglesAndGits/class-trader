import clsx from 'clsx'
import { AGENT_LABELS } from '../../lib/constants'
import ReasoningExpander from './ReasoningExpander'
import type { AgentInteraction } from '../../lib/types'

interface AgentCardProps {
  interaction: AgentInteraction
}

const AGENT_ACCENT: Record<string, string> = {
  REGIME_ANALYST: 'border-l-info',
  BULL: 'border-l-gain',
  BEAR: 'border-l-loss',
  RESEARCHER: 'border-l-warning',
  PORTFOLIO_MANAGER: 'border-l-info',
  DEGEN: 'border-l-warning',
}

export default function AgentCard({ interaction }: AgentCardProps) {
  const label = AGENT_LABELS[interaction.agent_type] ?? interaction.agent_type

  return (
    <div className={clsx('card border-l-2 space-y-2', AGENT_ACCENT[interaction.agent_type] ?? 'border-l-border')}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-text-primary text-sm font-medium">{label}</span>
          {!interaction.success && (
            <span className="badge-loss text-xs">failed</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-text-muted text-xs font-mono">
          {interaction.tokens_used && <span>{interaction.tokens_used.toLocaleString()} tok</span>}
          {interaction.latency_ms && <span>{interaction.latency_ms}ms</span>}
          {interaction.retry_count > 0 && (
            <span className="text-warning">{interaction.retry_count} retries</span>
          )}
        </div>
      </div>

      {interaction.parsed_output && (
        <div className="text-text-muted text-xs font-mono bg-bg rounded p-2 border border-border">
          <pre className="overflow-x-auto max-h-32 whitespace-pre-wrap">
            {JSON.stringify(interaction.parsed_output, null, 2)}
          </pre>
        </div>
      )}

      <ReasoningExpander
        label="View full prompt / response"
        content={`PROMPT:\n${interaction.prompt_text}\n\nRESPONSE:\n${interaction.response_text}`}
      />
    </div>
  )
}
