interface LoadingStateProps {
  message?: string
}

export default function LoadingState({ message = 'Loading...' }: LoadingStateProps) {
  return (
    <div className="flex items-center justify-center py-16 text-text-muted text-sm font-mono">
      <span className="animate-pulse">{message}</span>
    </div>
  )
}
