import { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'

// ── ET time helpers ───────────────────────────────────────────────────────────

function getEtHM(date: Date): { h: number; m: number; dow: number } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour: 'numeric',
    minute: '2-digit',
    weekday: 'long',
    hour12: false,
  }).formatToParts(date)

  const get = (type: string) => parts.find(p => p.type === type)?.value ?? '0'
  const dowMap: Record<string, number> = {
    Sunday: 0, Monday: 1, Tuesday: 2, Wednesday: 3,
    Thursday: 4, Friday: 5, Saturday: 6,
  }

  return {
    h: parseInt(get('hour')),
    m: parseInt(get('minute')),
    dow: dowMap[get('weekday')] ?? 0,
  }
}

// Compute the next scheduled pipeline run and how many minutes away it is.
// Schedule: Mon-Fri at 9:35 AM ET (morning) and 12:00 PM ET (noon).
function computeNextRun(now: Date): { label: string; minsUntil: number } {
  const { h, m, dow } = getEtHM(now)
  const current = h * 60 + m

  const MORNING = 9 * 60 + 35   // 9:35 AM
  const NOON    = 12 * 60        // 12:00 PM
  const DAY     = 24 * 60        // minutes in a day

  const isWeekday = dow >= 1 && dow <= 5

  if (isWeekday) {
    if (current < MORNING) {
      return { label: '9:35 AM ET', minsUntil: MORNING - current }
    }
    if (current < NOON) {
      return { label: '12:00 PM ET', minsUntil: NOON - current }
    }
    // After noon — next run is morning of next trading day
    const daysAhead = dow === 5 ? 3 : 1   // Friday → Monday
    return {
      label: '9:35 AM ET',
      minsUntil: (DAY - current) + MORNING + (daysAhead - 1) * DAY,
    }
  }

  // Weekend
  const daysAhead = dow === 6 ? 2 : 1   // Saturday → Monday, Sunday → Monday
  return {
    label: '9:35 AM ET',
    minsUntil: (DAY - current) + MORNING + (daysAhead - 1) * DAY,
  }
}

function formatCountdown(mins: number): string {
  if (mins < 1) return '< 1m'
  const h = Math.floor(mins / 60)
  const m = mins % 60
  if (h === 0) return `${m}m`
  if (m === 0) return `${h}h`
  return `${h}h ${m}m`
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function NextRunCountdown() {
  const [now, setNow] = useState(() => new Date())

  // Update every minute — precision to the minute is fine for a schedule display.
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(id)
  }, [])

  const { label, minsUntil } = computeNextRun(now)

  return (
    <div className="flex items-center gap-2 text-xs text-text-muted">
      <Clock size={12} className="shrink-0 text-info" />
      <span>
        Next run:{' '}
        <span className="font-mono text-text-secondary">{label}</span>
        {' · '}
        <span className="font-mono text-text-secondary">{formatCountdown(minsUntil)}</span>
      </span>
    </div>
  )
}
