import { useLocation } from 'react-router-dom'
import { Bell } from 'lucide-react'

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/agents': 'Agent Activity',
  '/portfolio': 'Portfolio',
  '/approvals': 'Trade Approvals',
  '/news': 'News & Sentiment',
  '/analytics': 'Analytics',
  '/settings': 'Settings',
}

export default function Header() {
  const { pathname } = useLocation()
  const title = PAGE_TITLES[pathname] ?? 'Class Trader'

  return (
    <header className="h-14 flex items-center justify-between px-6 border-b border-border bg-surface shrink-0">
      <h1 className="text-text-primary font-semibold text-base">{title}</h1>
      <div className="flex items-center gap-3">
        {/* Notification bell — wired up in Phase 5 */}
        <button className="text-text-muted hover:text-text-primary transition-colors p-1.5 rounded-md hover:bg-surface-2">
          <Bell size={16} />
        </button>
        <div className="text-text-muted text-xs font-mono border border-border px-2 py-1 rounded">
          PAPER
        </div>
      </div>
    </header>
  )
}
