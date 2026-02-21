import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Bot,
  Briefcase,
  CheckSquare,
  Newspaper,
  BarChart2,
  Settings,
  TrendingUp,
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/agents', icon: Bot, label: 'Agent Activity' },
  { to: '/portfolio', icon: Briefcase, label: 'Portfolio' },
  { to: '/approvals', icon: CheckSquare, label: 'Approvals' },
  { to: '/news', icon: Newspaper, label: 'News & Sentiment' },
  { to: '/analytics', icon: BarChart2, label: 'Analytics' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 flex flex-col h-full bg-surface border-r border-border">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-border">
        <div className="flex items-center gap-2.5">
          <TrendingUp size={20} className="text-gain" />
          <div>
            <div className="text-text-primary font-semibold text-sm leading-tight">Class Trader</div>
            <div className="text-text-muted text-xs leading-tight">under protest</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-4 py-2.5 mx-2 rounded-md text-sm transition-colors duration-150',
                isActive
                  ? 'bg-surface-2 text-text-primary'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-2/50'
              )
            }
          >
            <Icon size={16} className="shrink-0" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-border">
        <div className="text-text-muted text-xs font-mono">v0.1.0 · paper</div>
      </div>
    </aside>
  )
}
