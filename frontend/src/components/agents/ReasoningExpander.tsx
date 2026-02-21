import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'

interface ReasoningExpanderProps {
  label?: string
  content: string
}

export default function ReasoningExpander({ label = 'View reasoning', content }: ReasoningExpanderProps) {
  const [open, setOpen] = useState(false)

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-text-muted text-xs hover:text-text-secondary transition-colors"
      >
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        {open ? 'Hide' : label}
      </button>
      {open && (
        <div className="mt-2 p-3 bg-bg border border-border rounded text-xs text-text-secondary font-mono leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
          {content}
        </div>
      )}
    </div>
  )
}
