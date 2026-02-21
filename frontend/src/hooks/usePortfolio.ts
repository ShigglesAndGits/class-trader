import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Position, PortfolioSnapshot } from '../lib/types'

export function usePositions() {
  return useQuery({
    queryKey: ['positions'],
    queryFn: () => api.get<{ positions: Position[] }>('/api/portfolio/positions'),
    refetchInterval: 60_000,
    select: (data) => data.positions,
  })
}

export function usePortfolioSnapshots() {
  return useQuery({
    queryKey: ['portfolio-snapshots'],
    queryFn: () => api.get<{ snapshots: PortfolioSnapshot[] }>('/api/portfolio/snapshots'),
    select: (data) => data.snapshots,
  })
}
