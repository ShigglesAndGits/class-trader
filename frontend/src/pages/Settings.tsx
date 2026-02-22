import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import LoadingState from '../components/shared/LoadingState'
import AutoApproveToggle from '../components/dashboard/AutoApproveToggle'
import { formatDate } from '../lib/utils'
import type { WatchlistEntry, LLMProviderConfig, AgentLLMConfig } from '../lib/types'

interface SettingsData {
  auto_approve: boolean
  auto_approve_env: boolean
  alpaca_paper: boolean
  main_sleeve_allocation: number
  penny_sleeve_allocation: number
  max_position_pct_main: number
  max_position_dollars_penny: number
  min_confidence_main: number
  min_confidence_penny: number
  daily_loss_limit_main_pct: number
  daily_loss_limit_penny_pct: number
  consecutive_loss_pause: number
  timezone: string
  apis_configured: Record<string, boolean>
}

interface CircuitBreaker {
  id: number
  reason: string
  sleeve: string | null
  triggered_at: string
  resolved_at: string | null
  is_active: boolean
}

// Known Anthropic model IDs for datalist autocomplete
const ANTHROPIC_MODELS = [
  'claude-haiku-4-5-20251001',
  'claude-sonnet-4-6',
  'claude-opus-4-6',
  'claude-haiku-3-5-20241022',
]

export default function Settings() {
  const client = useQueryClient()

  const { data, isLoading } = useQuery<SettingsData>({
    queryKey: ['settings'],
    queryFn: () => api.get('/api/settings/'),
  })

  const { data: cbData } = useQuery<{ circuit_breakers: CircuitBreaker[] }>({
    queryKey: ['circuit-breakers'],
    queryFn: () => api.get('/api/settings/circuit-breakers'),
    refetchInterval: 60_000,
  })

  const { data: watchlistData, isLoading: watchlistLoading } = useQuery<{ tickers: WatchlistEntry[] }>({
    queryKey: ['watchlist'],
    queryFn: () => api.get('/api/watchlist/'),
    refetchInterval: 60_000,
  })

  const { data: providerData, refetch: refetchProvider } = useQuery<LLMProviderConfig>({
    queryKey: ['llm-provider'],
    queryFn: () => api.get('/api/settings/llm/provider'),
  })

  const { data: agentConfigsData, refetch: refetchAgents } = useQuery<{ agents: AgentLLMConfig[] }>({
    queryKey: ['llm-agents'],
    queryFn: () => api.get('/api/settings/llm/agents'),
  })

  const resolveBreaker = useMutation({
    mutationFn: (id: number) => api.post(`/api/settings/circuit-breakers/${id}/resolve`, {}),
    onSuccess: () => client.invalidateQueries({ queryKey: ['circuit-breakers'] }),
  })

  const removeEntry = useMutation({
    mutationFn: (id: number) => api.delete(`/api/watchlist/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['watchlist'] }),
  })

  const toggleEntry = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      api.patch(`/api/watchlist/${id}`, { is_active }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['watchlist'] }),
  })

  if (isLoading) return <LoadingState message="Loading settings..." />

  const apis = data?.apis_configured ?? {}
  const breakers = cbData?.circuit_breakers ?? []
  const activeBreakers = breakers.filter((b) => b.is_active)
  const watchlist = watchlistData?.tickers ?? []
  const agentConfigs = agentConfigsData?.agents ?? []

  return (
    <div className="space-y-5 max-w-2xl">
      {/* Trading mode */}
      <div className="card">
        <div className="card-header">Trading Mode</div>
        <div className="space-y-4">
          <div className="flex items-center justify-between py-1.5">
            <div>
              <span className="text-text-secondary text-sm">Alpaca Mode</span>
              <p className="text-text-muted text-xs mt-0.5">
                {data?.alpaca_paper
                  ? 'Paper trading — no real money at risk.'
                  : 'Live trading — real capital deployed.'}
              </p>
            </div>
            <span className={data?.alpaca_paper ? 'badge-info' : 'badge-loss'}>
              {data?.alpaca_paper ? 'Paper' : 'LIVE'}
            </span>
          </div>
          <div className="border-t border-border pt-4">
            <AutoApproveToggle enabled={data?.auto_approve ?? false} />
            {data?.auto_approve !== data?.auto_approve_env && (
              <p className="text-text-muted text-xs mt-2">
                Runtime value differs from <span className="font-mono">.env</span> (resets on restart).
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Circuit breakers */}
      {(activeBreakers.length > 0 || breakers.length > 0) && (
        <div className="card">
          <div className="card-header">
            Circuit Breakers
            {activeBreakers.length > 0 && (
              <span className="ml-2 badge-loss">{activeBreakers.length} active</span>
            )}
          </div>
          {breakers.length === 0 ? (
            <div className="text-text-muted text-sm py-4 text-center">
              No circuit breakers triggered. Everything is fine. Probably.
            </div>
          ) : (
            <div className="space-y-2">
              {breakers.map((b) => (
                <div
                  key={b.id}
                  className={clsx(
                    'flex items-start justify-between gap-3 p-3 rounded-lg border',
                    b.is_active ? 'border-loss/40 bg-loss/5' : 'border-border bg-surface-2/30'
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      {b.sleeve && (
                        <span className="text-xs font-mono text-text-muted">{b.sleeve}</span>
                      )}
                      <span className={clsx('text-xs', b.is_active ? 'text-loss' : 'text-text-muted')}>
                        {b.is_active ? 'ACTIVE' : 'resolved'}
                      </span>
                    </div>
                    <p className="text-text-secondary text-sm">{b.reason}</p>
                    <p className="text-text-muted text-xs mt-0.5 font-mono">
                      {formatDate(b.triggered_at)}
                      {b.resolved_at && ` → resolved ${formatDate(b.resolved_at)}`}
                    </p>
                  </div>
                  {b.is_active && (
                    <button
                      onClick={() => resolveBreaker.mutate(b.id)}
                      disabled={resolveBreaker.isPending}
                      className="btn-ghost text-xs border border-border shrink-0 disabled:opacity-50"
                    >
                      Resolve
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Watchlist */}
      <div className="card">
        <div className="card-header">Watchlist</div>
        {watchlistLoading ? (
          <LoadingState message="Loading watchlist..." />
        ) : (
          <>
            <div className="space-y-1 mb-4">
              {watchlist.length === 0 ? (
                <div className="text-text-muted text-sm py-4 text-center">
                  No tickers configured. Run <span className="font-mono">init_watchlist.py</span> to seed defaults.
                </div>
              ) : (
                watchlist.map((entry) => (
                  <WatchlistRow
                    key={entry.id}
                    entry={entry}
                    onToggle={(id, active) => toggleEntry.mutate({ id, is_active: active })}
                    onRemove={(id) => removeEntry.mutate(id)}
                    isPending={toggleEntry.isPending || removeEntry.isPending}
                  />
                ))
              )}
            </div>
            <AddTickerForm onAdded={() => client.invalidateQueries({ queryKey: ['watchlist'] })} />
          </>
        )}
      </div>

      {/* LLM & Agents */}
      <div className="card">
        <div className="card-header">LLM &amp; Agents</div>

        {/* Provider sub-section */}
        <LLMProviderSection
          config={providerData ?? null}
          onSaved={() => refetchProvider()}
        />

        {/* Per-agent config */}
        {agentConfigs.length > 0 && (
          <div className="mt-5 pt-5 border-t border-border">
            <p className="text-text-secondary text-xs font-medium uppercase tracking-wider mb-3">
              Per-Agent Config
            </p>
            <div className="space-y-2">
              {agentConfigs.map((cfg) => (
                <AgentConfigRow
                  key={cfg.agent_type}
                  config={cfg}
                  onSaved={() => refetchAgents()}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Risk parameters */}
      <div className="card">
        <div className="card-header">Risk Parameters</div>
        <div className="space-y-0">
          {[
            ['Main Sleeve Allocation', `$${data?.main_sleeve_allocation ?? '—'}`],
            ['Penny Sleeve Allocation', `$${data?.penny_sleeve_allocation ?? '—'}`],
            ['Max Position (Main)', `${data?.max_position_pct_main ?? '—'}%`],
            ['Max Position (Penny)', `$${data?.max_position_dollars_penny ?? '—'}`],
            ['Min Confidence (Main)', data?.min_confidence_main ?? '—'],
            ['Min Confidence (Penny)', data?.min_confidence_penny ?? '—'],
            ['Daily Loss Limit (Main)', `${data?.daily_loss_limit_main_pct ?? '—'}%`],
            ['Daily Loss Limit (Penny)', `${data?.daily_loss_limit_penny_pct ?? '—'}%`],
            ['Consecutive Loss Pause', `${data?.consecutive_loss_pause ?? '—'} trades`],
            ['Timezone', data?.timezone ?? '—'],
          ].map(([label, value]) => (
            <div
              key={label}
              className="flex items-center justify-between py-2 border-b border-border last:border-0"
            >
              <span className="text-text-secondary text-sm">{label}</span>
              <span className="text-text-primary text-sm font-mono">{String(value)}</span>
            </div>
          ))}
        </div>
        <p className="text-text-muted text-xs mt-3">
          Risk limits are enforced in code, not prompts. Edit <span className="font-mono">.env</span> and restart to change them.
        </p>
      </div>

      {/* API connections */}
      <div className="card">
        <div className="card-header">API Connections</div>
        <div className="space-y-0">
          {Object.entries(apis).map(([name, ok]) => (
            <div
              key={name}
              className="flex items-center justify-between py-2 border-b border-border last:border-0"
            >
              <span className="text-text-secondary text-sm capitalize">
                {name.replace(/_/g, ' ')}
              </span>
              <span className={ok ? 'badge-gain' : 'badge-loss'}>
                {ok ? 'configured' : 'missing'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── LLM Provider Section ────────────────────────────────────────────────────

function LLMProviderSection({
  config,
  onSaved,
}: {
  config: LLMProviderConfig | null
  onSaved: () => void
}) {
  const [provider, setProvider] = useState<'anthropic' | 'openai'>(config?.provider ?? 'anthropic')
  const [baseUrl, setBaseUrl] = useState(config?.openai_base_url ?? '')
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  // Sync from query if config loads after mount
  if (config && config.provider !== provider && !saving) {
    setProvider(config.provider)
    setBaseUrl(config.openai_base_url ?? '')
  }

  async function handleSave() {
    setSaving(true)
    setError('')
    try {
      await api.put('/api/settings/llm/provider', {
        provider,
        openai_base_url: baseUrl || null,
        openai_api_key: apiKey || null,
      })
      setSaved(true)
      setApiKey('')
      onSaved()
      setTimeout(() => setSaved(false), 2000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const inputCls = clsx(
    'w-full bg-surface-2 border border-border rounded px-3 py-1.5',
    'text-text-primary text-sm placeholder:text-text-muted',
    'focus:outline-none focus:border-info/50'
  )

  return (
    <div className="space-y-3">
      {/* Provider toggle */}
      <div className="flex gap-1 bg-surface-2 rounded-md p-0.5 border border-border w-fit">
        {(['anthropic', 'openai'] as const).map((p) => (
          <button
            key={p}
            onClick={() => setProvider(p)}
            className={clsx(
              'px-3 py-1 rounded text-sm transition-colors',
              provider === p
                ? 'bg-info/15 text-info border border-info/30'
                : 'text-text-secondary hover:text-text-primary'
            )}
          >
            {p === 'anthropic' ? 'Anthropic' : 'OpenAI-compatible'}
          </button>
        ))}
      </div>

      {/* OpenAI-compatible fields */}
      {provider === 'openai' && (
        <div className="space-y-2 pl-1">
          <div className="p-2.5 rounded-md bg-warning/5 border border-warning/30 text-xs text-warning">
            Structured output reliability varies by model. Local models may produce schema errors.
            Explorer mode always requires Anthropic.
          </div>
          <div>
            <label className="text-text-muted text-xs block mb-1">Base URL</label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://localhost:11434/v1"
              className={inputCls}
            />
          </div>
          <div>
            <label className="text-text-muted text-xs block mb-1">
              API Key{' '}
              {config?.has_api_key && (
                <span className="text-gain">•••••• (set — leave blank to keep)</span>
              )}
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={config?.has_api_key ? '(unchanged)' : 'sk-… or leave blank for Ollama'}
              className={inputCls}
            />
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary text-sm disabled:opacity-50"
        >
          {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save Provider'}
        </button>
        {error && <span className="text-loss text-xs">{error}</span>}
      </div>
    </div>
  )
}

// ── Per-Agent Config Row ────────────────────────────────────────────────────

function AgentConfigRow({
  config,
  onSaved,
}: {
  config: AgentLLMConfig
  onSaved: () => void
}) {
  const [model, setModel] = useState(config.model)
  const [maxTokens, setMaxTokens] = useState(config.max_tokens)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [showPrompt, setShowPrompt] = useState(false)
  const [promptText, setPromptText] = useState(config.effective_prompt)
  const [savingPrompt, setSavingPrompt] = useState(false)
  const [promptSaved, setPromptSaved] = useState(false)
  const [promptError, setPromptError] = useState('')

  async function handleSaveConfig() {
    if (maxTokens < 256) {
      setError('Min 256 tokens')
      return
    }
    setSaving(true)
    setError('')
    try {
      await api.put(`/api/settings/llm/agents/${config.agent_type}`, {
        model,
        max_tokens: maxTokens,
      })
      setSaved(true)
      onSaved()
      setTimeout(() => setSaved(false), 2000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function handleSavePrompt() {
    setSavingPrompt(true)
    setPromptError('')
    try {
      await api.put(`/api/settings/llm/agents/${config.agent_type}/prompt`, {
        prompt: promptText,
      })
      setPromptSaved(true)
      onSaved()
      setTimeout(() => setPromptSaved(false), 2000)
    } catch (e: unknown) {
      setPromptError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSavingPrompt(false)
    }
  }

  async function handleResetPrompt() {
    setSavingPrompt(true)
    setPromptError('')
    try {
      await api.delete(`/api/settings/llm/agents/${config.agent_type}/prompt`)
      setPromptText(config.default_prompt)
      setPromptSaved(true)
      onSaved()
      setTimeout(() => setPromptSaved(false), 2000)
    } catch (e: unknown) {
      setPromptError(e instanceof Error ? e.message : 'Reset failed')
    } finally {
      setSavingPrompt(false)
    }
  }

  const inputCls = clsx(
    'bg-surface-2 border border-border rounded px-2 py-1',
    'text-text-primary text-sm placeholder:text-text-muted',
    'focus:outline-none focus:border-info/50'
  )

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="flex items-center gap-3 px-3 py-2">
        {/* Agent label */}
        <span className="text-text-secondary text-sm w-36 shrink-0">{config.label}</span>

        {/* Model input */}
        <div className="flex-1">
          <input
            list="anthropic-models"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="model-id"
            className={clsx(inputCls, 'w-full font-mono text-xs')}
          />
          <datalist id="anthropic-models">
            {ANTHROPIC_MODELS.map((m) => <option key={m} value={m} />)}
          </datalist>
        </div>

        {/* Max tokens */}
        <input
          type="number"
          value={maxTokens}
          onChange={(e) => setMaxTokens(Number(e.target.value))}
          min={256}
          step={256}
          className={clsx(inputCls, 'w-24 font-mono text-xs text-right')}
          title="Max tokens"
        />

        {/* Prompt status */}
        <span
          className={config.has_custom_prompt ? 'badge-warning text-xs' : 'badge-info text-xs'}
          title={config.has_custom_prompt ? `Custom · last edited ${config.updated_at ?? '—'}` : 'Using default prompt'}
        >
          {config.has_custom_prompt ? 'Custom' : 'Default'}
        </span>

        {/* Prompt toggle */}
        <button
          onClick={() => setShowPrompt((v) => !v)}
          className="text-text-muted text-xs hover:text-text-primary transition-colors shrink-0"
        >
          {showPrompt ? 'Hide' : 'Edit'} prompt
        </button>

        {/* Save config button */}
        <button
          onClick={handleSaveConfig}
          disabled={saving}
          className="btn-ghost text-xs border border-border shrink-0 disabled:opacity-50"
        >
          {saving ? '…' : saved ? '✓' : 'Save'}
        </button>
      </div>

      {error && (
        <p className="text-loss text-xs px-3 pb-1">{error}</p>
      )}

      {/* Inline prompt editor */}
      {showPrompt && (
        <div className="border-t border-border bg-surface-2/30 p-3 space-y-2">
          <textarea
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
            rows={12}
            className={clsx(
              'w-full bg-surface border border-border rounded px-3 py-2 resize-y',
              'text-text-primary text-xs font-mono',
              'focus:outline-none focus:border-info/50'
            )}
          />
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={handleSavePrompt}
              disabled={savingPrompt}
              className="btn-primary text-xs disabled:opacity-50"
            >
              {savingPrompt ? 'Saving…' : promptSaved ? 'Saved ✓' : 'Save Prompt'}
            </button>
            {config.has_custom_prompt && (
              <button
                onClick={handleResetPrompt}
                disabled={savingPrompt}
                className="btn-ghost text-xs border border-border disabled:opacity-50"
              >
                Reset to default
              </button>
            )}
            {promptError && <span className="text-loss text-xs">{promptError}</span>}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Watchlist components ────────────────────────────────────────────────────

function WatchlistRow({
  entry,
  onToggle,
  onRemove,
  isPending,
}: {
  entry: WatchlistEntry
  onToggle: (id: number, active: boolean) => void
  onRemove: (id: number) => void
  isPending: boolean
}) {
  const sleeveColor: Record<string, string> = {
    MAIN: 'badge-info',
    PENNY: 'badge-warning',
    BENCHMARK: 'text-text-muted text-xs border border-border px-1.5 py-0.5 rounded',
  }

  return (
    <div
      className={clsx(
        'flex items-center justify-between gap-3 px-2 py-1.5 rounded',
        !entry.is_active && 'opacity-40'
      )}
    >
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <span className="font-mono text-text-primary text-sm w-14">{entry.ticker}</span>
        <span className={sleeveColor[entry.sleeve] ?? 'badge-info'}>{entry.sleeve}</span>
        {entry.notes && (
          <span className="text-text-muted text-xs truncate">{entry.notes}</span>
        )}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <button
          onClick={() => onToggle(entry.id, !entry.is_active)}
          disabled={isPending}
          className="btn-ghost text-xs border border-border disabled:opacity-50"
        >
          {entry.is_active ? 'Pause' : 'Resume'}
        </button>
        <button
          onClick={() => onRemove(entry.id)}
          disabled={isPending}
          className="text-loss text-xs hover:text-loss/70 transition-colors disabled:opacity-50 px-1.5 py-1"
          title="Remove ticker"
        >
          ✕
        </button>
      </div>
    </div>
  )
}

function AddTickerForm({ onAdded }: { onAdded: () => void }) {
  const [ticker, setTicker] = useState('')
  const [sleeve, setSleeve] = useState<'MAIN' | 'PENNY'>('MAIN')
  const [error, setError] = useState('')

  const add = useMutation({
    mutationFn: () => api.post('/api/watchlist/', { ticker: ticker.toUpperCase().trim(), sleeve }),
    onSuccess: () => {
      setTicker('')
      setError('')
      onAdded()
    },
    onError: (err: Error) => {
      setError(err.message ?? 'Failed to add ticker.')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!ticker.trim()) return
    add.mutate()
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2 pt-2 border-t border-border">
      <input
        type="text"
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        placeholder="TICKER"
        maxLength={10}
        className={clsx(
          'flex-1 bg-surface-2 border border-border rounded px-3 py-1.5',
          'text-text-primary text-sm font-mono placeholder:text-text-muted',
          'focus:outline-none focus:border-info/50'
        )}
      />
      <select
        value={sleeve}
        onChange={(e) => setSleeve(e.target.value as 'MAIN' | 'PENNY')}
        className={clsx(
          'bg-surface-2 border border-border rounded px-2 py-1.5',
          'text-text-secondary text-sm focus:outline-none focus:border-info/50'
        )}
      >
        <option value="MAIN">Main</option>
        <option value="PENNY">Penny</option>
      </select>
      <button
        type="submit"
        disabled={!ticker.trim() || add.isPending}
        className="btn-primary text-sm disabled:opacity-50"
      >
        Add
      </button>
      {error && <span className="text-loss text-xs">{error}</span>}
    </form>
  )
}
