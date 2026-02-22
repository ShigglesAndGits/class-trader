import { useState } from 'react'
import { Search, Newspaper, Compass } from 'lucide-react'
import clsx from 'clsx'
import type { QueryMode } from '../../lib/types'

interface Props {
  onSubmit: (query: string, mode: QueryMode) => void
  isLoading: boolean
  disabled?: boolean
}

const MODES: { key: QueryMode; icon: typeof Search; label: string; description: string }[] = [
  {
    key: 'NEWS_SCAN',
    icon: Newspaper,
    label: 'News Scan',
    description: 'Scan Finnhub headlines for candidates matching your theme.',
  },
  {
    key: 'EXPLORE',
    icon: Compass,
    label: 'Explore',
    description:
      'Let Sonnet search news, check market movers, and pick candidates itself.',
  },
]

export default function QueryInput({ onSubmit, isLoading, disabled }: Props) {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<QueryMode>('EXPLICIT')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || isLoading || disabled) return
    onSubmit(trimmed, mode)
  }

  function toggleMode(m: QueryMode) {
    setMode(prev => (prev === m ? 'EXPLICIT' : m))
  }

  const activeMode = MODES.find(m => m.key === mode)

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search
            size={15}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
          />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder={
              mode === 'EXPLORE'
                ? 'cheap stocks with momentum this week…'
                : 'NVDA, TSLA, META — or describe a theme…'
            }
            disabled={isLoading || disabled}
            className={clsx(
              'w-full pl-9 pr-3 py-2.5 bg-surface border border-border rounded-md',
              'text-sm text-text-primary placeholder:text-text-muted',
              'focus:outline-none focus:ring-1 focus:ring-info/50 focus:border-info/50',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          />
        </div>

        {/* Mode toggles */}
        {MODES.map(({ key, icon: Icon, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => toggleMode(key)}
            title={MODES.find(m => m.key === key)?.description}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-2 rounded-md text-sm transition-colors border',
              mode === key
                ? 'bg-info/15 border-info/40 text-info'
                : 'bg-surface-2 border-border text-text-secondary hover:text-text-primary hover:bg-surface-2/70',
            )}
          >
            <Icon size={14} />
            <span className="hidden sm:inline">{label}</span>
          </button>
        ))}

        <button
          type="submit"
          disabled={!query.trim() || isLoading || disabled}
          className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
        >
          {isLoading ? 'Starting…' : 'Research'}
        </button>
      </div>

      {activeMode ? (
        <p className="text-xs text-text-muted pl-1">{activeMode.description}</p>
      ) : (
        <p className="text-xs text-text-muted pl-1">
          Tip: 3–4 tickers works best — longer lists may hit token limits.
        </p>
      )}
    </form>
  )
}
