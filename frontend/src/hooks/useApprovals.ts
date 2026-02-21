import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { TradeDecision } from '../lib/types'

export function usePendingApprovals() {
  return useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => api.get<{ pending: TradeDecision[] }>('/api/approvals/pending'),
    refetchInterval: 15_000,
    select: (data) => data.pending,
  })
}

export function useApprove() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (tradeId: number) => api.post(`/api/approvals/${tradeId}/approve`, {}),
    onSuccess: () => client.invalidateQueries({ queryKey: ['approvals'] }),
  })
}

export function useReject() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (tradeId: number) => api.post(`/api/approvals/${tradeId}/reject`, {}),
    onSuccess: () => client.invalidateQueries({ queryKey: ['approvals'] }),
  })
}
