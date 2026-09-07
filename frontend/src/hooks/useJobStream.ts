// Subscribes to /ws/{kind}/{id}. The backend replays the whole event log to
// every new subscriber, so a reconnect simply resets and replays; there is no
// partial state to merge and no closure can go stale because every frame is
// appended to one array and derived views are computed from it.
import { useCallback, useEffect, useRef, useState } from 'react'
import { jobSocketUrl } from '../api/client'
import type { JobFrame, TrialEvent } from '../api/types'

export type StreamStatus = 'idle' | 'connecting' | 'live' | 'done' | 'error' | 'disconnected'

export interface JobStream<R> {
  status: StreamStatus
  events: TrialEvent[]
  result: R | null
  error: { message: string; setupError: boolean; cancelled: boolean } | null
  reconnect: () => void
  attempts: number
}

const MAX_AUTO_RETRIES = 3

export function useJobStream<R>(kind: 'experiment' | 'threshold', id: string | null): JobStream<R> {
  const [status, setStatus] = useState<StreamStatus>('idle')
  const [events, setEvents] = useState<TrialEvent[]>([])
  const [result, setResult] = useState<R | null>(null)
  const [error, setError] = useState<JobStream<R>['error']>(null)
  const [attempts, setAttempts] = useState(0)
  const [generation, setGeneration] = useState(0)
  const retriesRef = useRef(0)

  const reconnect = useCallback(() => {
    retriesRef.current = 0
    setGeneration((g) => g + 1)
  }, [])

  useEffect(() => {
    if (!id) {
      setStatus('idle')
      setEvents([])
      setResult(null)
      setError(null)
      return
    }
    let disposed = false
    let terminal = false
    let retryTimer: number | undefined
    const ws = new WebSocket(jobSocketUrl(kind, id))
    const buffer: TrialEvent[] = []
    let flushTimer: number | undefined

    setStatus('connecting')
    setEvents([])
    setResult(null)
    setError(null)

    const flush = () => {
      flushTimer = undefined
      if (buffer.length === 0) return
      const batch = buffer.splice(0, buffer.length)
      setEvents((prev) => [...prev, ...batch])
    }

    ws.onopen = () => {
      if (!disposed) setStatus('live')
    }
    ws.onmessage = (e) => {
      if (disposed) return
      let frame: JobFrame
      try {
        frame = JSON.parse(e.data) as JobFrame
      } catch {
        return // "pong" and other non-JSON keepalives
      }
      switch (frame.type) {
        case 'connected':
          break
        case 'event': {
          const { type: _t, ...ev } = frame
          buffer.push(ev as TrialEvent)
          if (flushTimer === undefined) flushTimer = window.setTimeout(flush, 32)
          break
        }
        case 'done':
          flush()
          terminal = true
          setResult(frame.result as R)
          setStatus('done')
          ws.close()
          break
        case 'error':
          flush()
          terminal = true
          setError({
            message: frame.message,
            setupError: Boolean(frame.setup_error),
            cancelled: Boolean(frame.cancelled),
          })
          setStatus('error')
          ws.close()
          break
      }
    }
    ws.onclose = (ev) => {
      if (disposed || terminal) return
      if (ev.code === 4404) {
        terminal = true
        setError({ message: `The server no longer knows job ${id}. It may have been evicted.`, setupError: false, cancelled: false })
        setStatus('error')
        return
      }
      if (retriesRef.current < MAX_AUTO_RETRIES) {
        retriesRef.current += 1
        setAttempts(retriesRef.current)
        retryTimer = window.setTimeout(() => setGeneration((g) => g + 1), 800 * retriesRef.current)
      } else {
        setStatus('disconnected')
      }
    }
    ws.onerror = () => {
      /* onclose follows and handles reconnect */
    }

    return () => {
      disposed = true
      if (flushTimer !== undefined) window.clearTimeout(flushTimer)
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
      // Closing a socket that is still connecting makes browsers log a
      // warning (StrictMode mounts effects twice); let it open, then close.
      if (ws.readyState === WebSocket.CONNECTING) ws.onopen = () => ws.close()
      else if (ws.readyState === WebSocket.OPEN) ws.close()
    }
  }, [kind, id, generation])

  return { status, events, result, error, reconnect, attempts }
}
