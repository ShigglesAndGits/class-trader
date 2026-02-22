/**
 * TypeScript types matching the backend Pydantic schemas.
 * Keep in sync with backend/app/schemas/.
 */

// ── Market regime ────────────────────────────────────────────────────────────

export type Regime = 'TRENDING_UP' | 'TRENDING_DOWN' | 'RANGING' | 'HIGH_VOLATILITY'

export interface RegimeAssessment {
  regime: Regime
  confidence: number
  reasoning: string
  key_indicators: string[]
}

// ── Retail sentiment ─────────────────────────────────────────────────────────

export interface RetailSentiment {
  ticker: string
  mention_count_24h: number
  mention_velocity: number
  avg_sentiment: number
  hype_score: number
  top_posts: string[]
  subreddits: string[]
  caution_flags: string[]
}

// ── Trade decisions ──────────────────────────────────────────────────────────

export type TradeAction = 'BUY' | 'SELL' | 'HOLD'
export type TradeStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'FAILED' | 'SKIPPED'
export type Sleeve = 'MAIN' | 'PENNY'

export interface TradeDecision {
  id: number
  ticker: string
  sleeve: Sleeve
  action: TradeAction
  confidence: number
  position_size_pct: number
  reasoning: string
  stop_loss_pct?: number
  take_profit_pct?: number
  status: TradeStatus
  wash_sale_flagged: boolean
  created_at: string
  resolved_at?: string
  resolved_by?: 'AUTO' | 'MANUAL'
}

// ── Portfolio ────────────────────────────────────────────────────────────────

export interface Position {
  ticker: string
  sleeve: Sleeve
  qty: number
  current_price: number
  market_value: number
  cost_basis: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  entry_price: number
}

export interface PortfolioSnapshot {
  timestamp: string
  main_equity: number
  penny_equity: number
  total_equity: number
  cash_balance: number
  spy_benchmark_value?: number
  daily_pnl?: number
  daily_pnl_pct?: number
}

// ── Pipeline ─────────────────────────────────────────────────────────────────

export type RunType = 'MORNING' | 'NOON' | 'NEWS_TRIGGER' | 'MANUAL' | 'DISCOVERY'
export type RunStatus = 'RUNNING' | 'COMPLETED' | 'FAILED' | 'PAUSED'
export type AgentType = 'REGIME_ANALYST' | 'BULL' | 'BEAR' | 'RESEARCHER' | 'PORTFOLIO_MANAGER' | 'DEGEN'

export interface PipelineRun {
  id: number
  run_type: RunType
  started_at: string
  completed_at?: string
  regime?: Regime
  regime_confidence?: number
  status: RunStatus
}

export interface AgentInteraction {
  id: number
  pipeline_run_id: number
  agent_type: AgentType
  prompt_text: string
  response_text: string
  parsed_output?: Record<string, unknown>
  tokens_used?: number
  latency_ms?: number
  retry_count?: number
  created_at: string
  success: boolean
}

// ── News ─────────────────────────────────────────────────────────────────────

export interface NewsItem {
  id: number
  ticker?: string
  headline: string
  summary?: string
  source?: string
  url?: string
  sentiment_score?: number
  published_at?: string
  triggered_analysis: boolean
}

// ── Watchlist ────────────────────────────────────────────────────────────────

export interface WatchlistEntry {
  id: number
  ticker: string
  sleeve: Sleeve | 'BENCHMARK'
  is_active: boolean
  notes?: string
  added_at: string
}

// ── LLM config ───────────────────────────────────────────────────────────────

export type LLMProvider = 'anthropic' | 'openai'

export interface LLMProviderConfig {
  provider: LLMProvider
  openai_base_url: string | null
  has_api_key: boolean
}

export interface AgentLLMConfig {
  agent_type: string
  label: string
  model: string
  max_tokens: number
  has_custom_prompt: boolean
  effective_prompt: string
  default_prompt: string
  updated_at: string | null
}

// ── Discovery ────────────────────────────────────────────────────────────────

export type DiscoveryAction = 'BUY' | 'CONSIDER' | 'AVOID'
export type DiscoveryStatus = 'RUNNING' | 'COMPLETED' | 'FAILED'
export type QueryMode = 'EXPLICIT' | 'NEWS_SCAN' | 'EXPLORE'

export interface DiscoveryRecommendation {
  action: DiscoveryAction
  ticker: string
  confidence: number
  position_size_pct: number
  reasoning: string
  stop_loss_pct?: number
  take_profit_pct?: number
  suggested_sleeve: Sleeve
}

export interface DiscoveryRecommendations {
  recommendations: DiscoveryRecommendation[]
  overall_thesis: string
  caveats: string[]
}

export interface DiscoveryChatMessage {
  role: 'user' | 'assistant'
  content: string
  ts: string
}

export type AgentStepStatus = 'pending' | 'running' | 'complete' | 'error'

export interface AgentStep {
  agent: string
  status: AgentStepStatus
  data?: Record<string, unknown>
}
