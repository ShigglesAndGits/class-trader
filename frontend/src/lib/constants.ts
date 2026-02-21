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
