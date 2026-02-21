import { useEffect, useRef, useCallback } from 'react'

type MessageHandler = (data: Record<string, unknown>) => void

export function useWebSocket(onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const ws = new WebSocket(`${protocol}//${host}/ws/updates`)

    ws.onopen = () => {
      console.debug('[WS] Connected')
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
      } catch {
        console.warn('[WS] Non-JSON message:', event.data)
      }
    }

    ws.onclose = () => {
      console.debug('[WS] Disconnected, reconnecting in 5s...')
      reconnectRef.current = setTimeout(connect, 5_000)
    }

    ws.onerror = (err) => {
      console.warn('[WS] Error:', err)
      ws.close()
    }

    wsRef.current = ws
  }, [onMessage])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
      wsRef.current?.close()
    }
  }, [connect])
}
