/**
 * Shared utility functions.
 */

/** Format a dollar amount with sign and 2 decimal places. */
export function formatDollar(value: number, showSign = false): string {
  const sign = showSign && value > 0 ? '+' : ''
  return `${sign}$${Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** Format a percentage with sign. */
export function formatPct(value: number, decimals = 2): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}%`
}

/** Format a confidence score as a percentage badge label. */
export function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`
}

/** Return the Tailwind color class for a P&L value. */
export function pnlColor(value: number): string {
  if (value > 0) return 'text-gain'
  if (value < 0) return 'text-loss'
  return 'text-text-secondary'
}

/** Format an ISO timestamp to a readable local time. */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Format an ISO timestamp to a readable date. */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}
