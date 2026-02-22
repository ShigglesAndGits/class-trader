export const REGIME_LABELS: Record<string, string> = {
  TRENDING_UP: 'Trending Up',
  TRENDING_DOWN: 'Trending Down',
  RANGING: 'Ranging',
  HIGH_VOLATILITY: 'High Volatility',
}

export const REGIME_COLORS: Record<string, string> = {
  TRENDING_UP: 'text-gain',
  TRENDING_DOWN: 'text-loss',
  RANGING: 'text-warning',
  HIGH_VOLATILITY: 'text-loss',
}

export const AGENT_LABELS: Record<string, string> = {
  REGIME_ANALYST: 'Regime Analyst',
  BULL: 'Bull Agent',
  BEAR: 'Bear Agent',
  RESEARCHER: 'Researcher',
  PORTFOLIO_MANAGER: 'Portfolio Manager',
  DEGEN: 'The Gambler',
}

export const ACTION_COLORS: Record<string, string> = {
  BUY: 'badge-gain',
  SELL: 'badge-loss',
  HOLD: 'badge-info',
}

export const DISCOVERY_AGENT_LABELS: Record<string, string> = {
  EXPLORER: 'Explorer',
  REGIME_ANALYST: 'Regime Analyst',
  BULL: 'Bull',
  BEAR: 'Bear',
  RESEARCHER: 'Researcher',
  DISCOVERY_PM: 'Portfolio Manager',
}

/** Pipeline order for non-explore sessions (no EXPLORER step). */
export const DISCOVERY_AGENT_ORDER = [
  'REGIME_ANALYST',
  'BULL',
  'BEAR',
  'RESEARCHER',
  'DISCOVERY_PM',
]

/** Pipeline order for EXPLORE sessions (Explorer runs first). */
export const DISCOVERY_AGENT_ORDER_EXPLORE = [
  'EXPLORER',
  'REGIME_ANALYST',
  'BULL',
  'BEAR',
  'RESEARCHER',
  'DISCOVERY_PM',
]

export const EXPLORER_TOOL_LABELS: Record<string, string> = {
  search_financial_news: 'Searching news',
  get_market_movers: 'Checking market movers',
  lookup_ticker: 'Looking up ticker',
}

export const DISCOVERY_ACTION_COLORS: Record<string, string> = {
  BUY: 'badge-gain',
  CONSIDER: 'badge-warning',
  AVOID: 'badge-loss',
}
