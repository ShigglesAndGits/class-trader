import type { AgentStep } from '../../lib/types'
import DiscoveryAgentCard from './DiscoveryAgentCard'

interface Props {
  steps: AgentStep[]
  currentAgent: string | null
}

export default function DiscoveryAgentTimeline({ steps, currentAgent }: Props) {
  return (
    <div className="space-y-2">
      {steps.map(step => (
        <DiscoveryAgentCard
          key={step.agent}
          step={step}
          isRunning={step.agent === currentAgent}
        />
      ))}
    </div>
  )
}
