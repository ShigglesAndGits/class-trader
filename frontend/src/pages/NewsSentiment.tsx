import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import LoadingState from '../components/shared/LoadingState'
import { formatDate } from '../lib/utils'

interface NewsItem {
  id: number
  ticker: string | null
  headline: string
  source: string | null
  url: string | null
  sentiment_score: number | null
  published_at: string | null
  triggered_analysis: boolean
}

interface RedditMention {
  id: number
  ticker: string
  subreddit: string
  post_title: string
  post_url: string | null
  post_score: number | null
  hype_score: number | null
  mention_velocity: number | null
  sentiment_score: number | null
  fetched_at: string
}

function sentimentColor(score: number | null): string {
  if (score == null) return 'text-text-muted'
  if (score > 0.3) return 'text-gain'
  if (score < -0.3) return 'text-loss'
  return 'text-warning'
}

function sentimentLabel(score: number | null): string {
  if (score == null) return '—'
  return score.toFixed(2)
}

export default function NewsSentiment() {
  const { data: newsData, isLoading: newsLoading } = useQuery<{ items: NewsItem[]; count: number }>({
    queryKey: ['news-feed'],
    queryFn: () => api.get('/api/news/feed?limit=30'),
    refetchInterval: 120_000,
  })

  const { data: retailData, isLoading: retailLoading } = useQuery<{ trending: RedditMention[]; count: number }>({
    queryKey: ['news-retail'],
    queryFn: () => api.get('/api/news/retail?limit=30'),
    refetchInterval: 300_000,
  })

  const news = newsData?.items ?? []
  const retail = retailData?.trending ?? []

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
      {/* News feed */}
      <div className="card">
        <div className="card-header">News Feed</div>
        {newsLoading ? (
          <LoadingState message="Loading news..." />
        ) : news.length === 0 ? (
          <div className="text-text-muted text-sm py-6 text-center">
            No news yet. Articles will appear after the next scheduled fetch.
          </div>
        ) : (
          <div className="space-y-3 divide-y divide-border">
            {news.map((item) => (
              <div key={item.id} className="pt-3 first:pt-0">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    {item.url ? (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-text-primary text-sm hover:text-info transition-colors leading-snug"
                      >
                        {item.headline}
                      </a>
                    ) : (
                      <p className="text-text-primary text-sm leading-snug">{item.headline}</p>
                    )}
                    <div className="flex items-center gap-2 mt-1 text-xs text-text-muted">
                      {item.ticker && (
                        <span className="font-mono text-text-secondary">{item.ticker}</span>
                      )}
                      {item.source && <span>{item.source}</span>}
                      {item.published_at && <span>{formatDate(item.published_at)}</span>}
                      {item.triggered_analysis && (
                        <span className="text-warning">triggered analysis</span>
                      )}
                    </div>
                  </div>
                  <span className={clsx('text-xs font-mono shrink-0 mt-0.5', sentimentColor(item.sentiment_score))}>
                    {sentimentLabel(item.sentiment_score)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* TendieBot / Retail Pulse */}
      <div className="card">
        <div className="card-header">TendieBot — Retail Pulse</div>
        {retailLoading ? (
          <LoadingState message="Loading retail sentiment..." />
        ) : retail.length === 0 ? (
          <div className="text-text-muted text-sm py-6 text-center">
            The apes are out there. We just can't hear them yet.
          </div>
        ) : (
          <div className="space-y-3 divide-y divide-border">
            {retail.map((m) => (
              <div key={m.id} className="pt-3 first:pt-0">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-mono text-text-primary font-semibold">{m.ticker}</span>
                      <span className="text-xs text-text-muted">r/{m.subreddit}</span>
                      {m.mention_velocity != null && m.mention_velocity >= 5 && (
                        <span className="text-loss text-xs font-mono">⚡ {m.mention_velocity.toFixed(1)}x spike</span>
                      )}
                    </div>
                    {m.post_url ? (
                      <a
                        href={m.post_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-text-secondary text-xs hover:text-info transition-colors line-clamp-2 leading-snug"
                      >
                        {m.post_title}
                      </a>
                    ) : (
                      <p className="text-text-secondary text-xs line-clamp-2 leading-snug">{m.post_title}</p>
                    )}
                    <div className="flex items-center gap-3 mt-1 text-xs text-text-muted font-mono">
                      {m.post_score != null && <span>↑{m.post_score}</span>}
                      {m.mention_velocity != null && (
                        <span>vel: {m.mention_velocity.toFixed(1)}x</span>
                      )}
                    </div>
                  </div>
                  {m.hype_score != null && (
                    <div className="shrink-0 text-right">
                      <div className={clsx(
                        'text-sm font-mono font-semibold',
                        m.hype_score >= 0.8 ? 'text-loss' :
                        m.hype_score >= 0.5 ? 'text-warning' : 'text-gain'
                      )}>
                        {(m.hype_score * 100).toFixed(0)}
                      </div>
                      <div className="text-text-muted text-xs">hype</div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
