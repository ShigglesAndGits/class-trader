import { useRef, useState } from 'react'
import { Send, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import type { DiscoveryChatMessage } from '../../lib/types'

interface Props {
  sessionId: number
  messages: DiscoveryChatMessage[]
  onNewMessages: (messages: DiscoveryChatMessage[]) => void
  onRebate: (newSessionId: number) => void
}

function formatTs(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

export default function DiscoveryChat({ sessionId, messages, onNewMessages, onRebate }: Props) {
  const [input, setInput] = useState('')
  const [rebate, setRebate] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setSending(true)
    setError(null)

    const optimisticUser: DiscoveryChatMessage = {
      role: 'user',
      content: text,
      ts: new Date().toISOString(),
    }
    onNewMessages([...messages, optimisticUser])
    setInput('')

    try {
      const res = await fetch(`/api/discovery/sessions/${sessionId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, rebate }),
      })
      if (!res.ok) throw new Error(await res.text())

      const data = (await res.json()) as { reply: string; rebate_session_id?: number }

      if (rebate && data.rebate_session_id) {
        onRebate(data.rebate_session_id)
        setRebate(false)
      } else {
        const assistantMsg: DiscoveryChatMessage = {
          role: 'assistant',
          content: data.reply,
          ts: new Date().toISOString(),
        }
        onNewMessages([...messages, optimisticUser, assistantMsg])
        setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
      }
    } catch {
      setError('Failed to send. Try again.')
      // Roll back optimistic message
      onNewMessages(messages)
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="card space-y-3">
      <p className="text-xs text-text-muted uppercase tracking-wide font-medium">Follow-up</p>

      {/* Conversation */}
      {messages.length > 0 && (
        <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={clsx('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}
            >
              <div
                className={clsx(
                  'max-w-[80%] rounded-lg px-3 py-2 text-sm leading-relaxed',
                  msg.role === 'user'
                    ? 'bg-info/15 text-text-primary'
                    : 'bg-surface-2 text-text-secondary',
                )}
              >
                <p>{msg.content}</p>
                <p className="text-xs text-text-muted mt-1">{formatTs(msg.ts)}</p>
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      {/* Input */}
      <div className="space-y-2">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={rebate ? 'Make your counter-argument…' : 'Ask a follow-up question…'}
          rows={2}
          className={clsx(
            'w-full px-3 py-2 bg-surface border border-border rounded-md resize-none',
            'text-sm text-text-primary placeholder:text-text-muted',
            'focus:outline-none focus:ring-1 focus:ring-info/50 focus:border-info/50',
          )}
        />

        <div className="flex items-center gap-3">
          {/* Re-debate toggle */}
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={rebate}
              onChange={e => setRebate(e.target.checked)}
              className="accent-info"
            />
            <span className="text-xs text-text-secondary flex items-center gap-1">
              <RefreshCw size={11} />
              Re-debate with this argument
            </span>
          </label>

          <button
            onClick={send}
            disabled={!input.trim() || sending}
            className="flex items-center gap-1.5 btn-primary text-sm ml-auto disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send size={13} />
            {sending ? 'Sending…' : rebate ? 'Re-debate' : 'Send'}
          </button>
        </div>

        {error && <p className="text-xs text-loss">{error}</p>}
        {rebate && (
          <p className="text-xs text-info/70">
            Re-debate creates a new analysis session with your argument injected into the Bull and Bear prompts.
          </p>
        )}
      </div>
    </div>
  )
}
