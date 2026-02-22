import { useCallback, useRef, useState } from 'react'
import { DISCOVERY_AGENT_ORDER, DISCOVERY_AGENT_ORDER_EXPLORE } from '../lib/constants'
import type { AgentStep, AgentStepStatus, DiscoveryRecommendations } from '../lib/types'

export interface DiscoveryStreamState {
  steps: AgentStep[]
  confirmedTickers: string[]
  recommendations: DiscoveryRecommendations | null
  isStreaming: boolean
  error: string | null
  /** The agent currently being analyzed (first pending step while streaming). */
  currentAgent: string | null
}

function initSteps(isExplore: boolean): AgentStep[] {
  const order = isExplore ? DISCOVERY_AGENT_ORDER_EXPLORE : DISCOVERY_AGENT_ORDER
  return order.map(agent => ({ agent, status: 'pending' as AgentStepStatus }))
}

export function useDiscoveryStream() {
  const esRef = useRef<EventSource | null>(null)
  const isExploreRef = useRef(false)

  const [state, setState] = useState<DiscoveryStreamState>({
    steps: initSteps(false),
    confirmedTickers: [],
    recommendations: null,
    isStreaming: false,
    error: null,
    currentAgent: null,
  })

  const reset = useCallback(() => {
    if (esRef.current) {
      esRef.current.close()
      esRef.current = null
    }
    isExploreRef.current = false
    setState({
      steps: initSteps(false),
      confirmedTickers: [],
      recommendations: null,
      isStreaming: false,
      error: null,
      currentAgent: null,
    })
  }, [])

  const startStream = useCallback((sessionId: number, isExplore = false) => {
    if (esRef.current) {
      esRef.current.close()
    }

    isExploreRef.current = isExplore
    const freshSteps = initSteps(isExplore)
    setState({
      steps: freshSteps,
      confirmedTickers: [],
      recommendations: null,
      isStreaming: true,
      error: null,
      currentAgent: freshSteps[0]?.agent ?? null,
    })

    const es = new EventSource(`/api/discovery/sessions/${sessionId}/stream`)
    esRef.current = es

    es.onmessage = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data as string) as {
          event: string
          data: Record<string, unknown>
        }
        const { event: eventType, data } = parsed

        // ── Explorer events (EXPLORE mode only) ────────────────────────
        if (eventType === 'explorer_tool_call') {
          setState(prev => {
            const steps = prev.steps.map(s => {
              if (s.agent !== 'EXPLORER') return s
              const toolCalls = [...((s.data?.toolCalls as unknown[]) ?? []), data]
              return { ...s, status: 'running' as AgentStepStatus, data: { ...s.data, toolCalls } }
            })
            return { ...prev, steps, currentAgent: 'EXPLORER' }
          })
        } else if (eventType === 'explorer_complete') {
          const tickers = (data.tickers as string[] | undefined) ?? []
          setState(prev => {
            const steps = prev.steps.map(s =>
              s.agent === 'EXPLORER'
                ? { ...s, status: 'complete' as AgentStepStatus, data }
                : s,
            )
            const next = steps.find(s => s.status === 'pending')?.agent ?? null
            return { ...prev, steps, confirmedTickers: tickers, currentAgent: next }
          })

        // ── Regular pipeline events ────────────────────────────────────
        } else if (eventType === 'data_ready') {
          setState(prev => ({
            ...prev,
            confirmedTickers:
              (data.tickers as string[] | undefined) ?? prev.confirmedTickers,
          }))
        } else if (eventType === 'agent_complete') {
          const agent = data.agent as string
          setState(prev => {
            const steps = prev.steps.map(s =>
              s.agent === agent ? { ...s, status: 'complete' as AgentStepStatus, data } : s,
            )
            const next = steps.find(s => s.status === 'pending')?.agent ?? null
            return { ...prev, steps, currentAgent: next }
          })
        } else if (eventType === 'pipeline_complete') {
          const recs = data.recommendations as DiscoveryRecommendations | undefined
          setState(prev => ({
            ...prev,
            recommendations: recs ?? null,
            isStreaming: false,
            currentAgent: null,
          }))
          es.close()
          esRef.current = null
        } else if (eventType === 'pipeline_error') {
          setState(prev => ({
            ...prev,
            error: (data.error as string | undefined) ?? 'Pipeline failed.',
            isStreaming: false,
            currentAgent: null,
          }))
          es.close()
          esRef.current = null
        }
      } catch {
        // ignore parse errors on non-JSON frames
      }
    }

    es.onerror = () => {
      setState(prev => ({
        ...prev,
        error: 'Lost connection to the pipeline.',
        isStreaming: false,
        currentAgent: null,
      }))
      es.close()
      esRef.current = null
    }
  }, [])

  const close = useCallback(() => {
    if (esRef.current) {
      esRef.current.close()
      esRef.current = null
    }
    setState(prev => ({ ...prev, isStreaming: false, currentAgent: null }))
  }, [])

  return { ...state, startStream, reset, close }
}
