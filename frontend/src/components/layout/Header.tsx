import { useLocation } from 'react-router-dom'
import { Bell, Menu } from 'lucide-react'

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/discover': 'Discover',
  '/agents': 'Agent Activity',
  '/portfolio': 'Portfolio',
  '/approvals': 'Trade Approvals',
  '/news': 'News & Sentiment',
  '/analytics': 'Analytics',
  '/settings': 'Settings',
}

interface HeaderProps {
  onMenuToggle: () => void
}

export default function Header({ onMenuToggle }: HeaderProps) {
  const { pathname } = useLocation()
  const title = PAGE_TITLES[pathname] ?? 'Class Trader'

  return (
    <header className="h-14 flex items-center justify-between px-4 md:px-6 border-b border-border bg-surface shrink-0">
      <div className="flex items-center gap-3">
        {/* Hamburger — mobile only */}
        <button
          onClick={onMenuToggle}
          className="md:hidden text-text-muted hover:text-text-primary transition-colors p-1.5 rounded-md hover:bg-surface-2"
          aria-label="Toggle menu"
        >
          <Menu size={18} />
        </button>
        <h1 className="text-text-primary font-semibold text-base">{title}</h1>
      </div>
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
