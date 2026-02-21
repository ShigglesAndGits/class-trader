import { useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../../api/client'

interface AutoApproveToggleProps {
  enabled: boolean
}

export default function AutoApproveToggle({ enabled }: AutoApproveToggleProps) {
  const client = useQueryClient()

  const toggle = useMutation({
    mutationFn: (next: boolean) =>
      api.put('/api/settings/auto-approve', { enabled: next }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['dashboard'] })
      client.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-col">
        <span className="text-text-primary text-sm font-medium">Auto-Approve</span>
        <span className="text-text-muted text-xs">
          {enabled ? 'Trades execute automatically' : 'All trades require manual review'}
        </span>
      </div>

      <button
        onClick={() => toggle.mutate(!enabled)}
        disabled={toggle.isPending}
        aria-label={`Auto-approve is ${enabled ? 'on' : 'off'}. Click to toggle.`}
        className={clsx(
          'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2',
          'transition-colors duration-200 focus:outline-none disabled:opacity-50',
          enabled
            ? 'border-gain bg-gain'
            : 'border-border bg-surface-2'
        )}
      >
        <span
          className={clsx(
            'inline-block h-4 w-4 rounded-full bg-white shadow-sm',
            'transition-transform duration-200 mt-0.5',
            enabled ? 'translate-x-5' : 'translate-x-0.5'
          )}
        />
      </button>
    </div>
  )
}
