import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import LoadingState from '../components/shared/LoadingState'
import ApprovalCard from '../components/approvals/ApprovalCard'
import { usePendingApprovals } from '../hooks/useApprovals'

export default function Approvals() {
  const client = useQueryClient()
  const { data: trades, isLoading } = usePendingApprovals()

  const approve = useMutation({
    mutationFn: (id: number) => api.post(`/api/approvals/${id}/approve`, {}),
    onSuccess: () => client.invalidateQueries({ queryKey: ['approvals'] }),
  })

  const reject = useMutation({
    mutationFn: (id: number) => api.post(`/api/approvals/${id}/reject`, {}),
    onSuccess: () => client.invalidateQueries({ queryKey: ['approvals'] }),
  })

  const bulkApprove = useMutation({
    mutationFn: () =>
      api.post('/api/approvals/bulk-approve', (trades ?? []).map((t) => t.id)),
    onSuccess: () => client.invalidateQueries({ queryKey: ['approvals'] }),
  })

  const bulkReject = useMutation({
    mutationFn: () =>
      api.post('/api/approvals/bulk-reject', (trades ?? []).map((t) => t.id)),
    onSuccess: () => client.invalidateQueries({ queryKey: ['approvals'] }),
  })

  const anyPending = approve.isPending || reject.isPending || bulkApprove.isPending || bulkReject.isPending

  if (isLoading) return <LoadingState message="Loading approval queue..." />

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-text-primary font-medium">
            {trades?.length ? `${trades.length} trade${trades.length !== 1 ? 's' : ''} awaiting review` : 'Approval Queue'}
          </h2>
          <p className="text-text-muted text-xs mt-0.5">
            Review agent reasoning before committing capital.
          </p>
        </div>

        {(trades?.length ?? 0) > 1 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => bulkReject.mutate()}
              disabled={anyPending}
              className="btn-ghost text-xs border border-border disabled:opacity-50"
            >
              Reject all
            </button>
            <button
              onClick={() => bulkApprove.mutate()}
              disabled={anyPending}
              className="btn-primary text-xs disabled:opacity-50"
            >
              Approve all
            </button>
          </div>
        )}
      </div>

      {!trades?.length ? (
        <div className="card text-center py-12">
          <div className="text-text-muted text-sm">
            Nothing to approve. The algorithms are taking a breather.
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {trades.map((trade) => (
            <ApprovalCard
              key={trade.id}
              trade={trade}
              onApprove={(id) => approve.mutate(id)}
              onReject={(id) => reject.mutate(id)}
              isPending={anyPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}
