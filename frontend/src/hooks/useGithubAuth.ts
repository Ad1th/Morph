// GitHub device flow, kept out of the Projects screen. The token lives only in
// component memory: it is never written to localStorage.
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../api/client'
import type { GithubRepo } from '../api/types'

export type GithubAuthState =
  | { phase: 'idle' }
  | { phase: 'server'; source: string }
  | { phase: 'requesting' }
  | { phase: 'waiting'; userCode: string; verificationUri: string }
  | { phase: 'authorized'; source: 'device' | 'token' }
  | { phase: 'error'; message: string }

export function useGithubAuth() {
  const [state, setState] = useState<GithubAuthState>({ phase: 'idle' })
  const [token, setToken] = useState('')
  const [repos, setRepos] = useState<GithubRepo[]>([])
  const [reposError, setReposError] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)
  const mounted = useRef(true)

  const stopPolling = useCallback(() => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    api
      .githubAuthStatus()
      .then((s) => {
        if (mounted.current && s.authenticated) setState({ phase: 'server', source: s.source })
      })
      .catch(() => {
        /* no status route on this server: the device flow still works */
      })
    return () => {
      mounted.current = false
      stopPolling()
    }
  }, [stopPolling])

  const loadRepos = useCallback(async (explicitToken?: string) => {
    setReposError(null)
    try {
      const list = await api.fetchGithubRepos(explicitToken || undefined)
      if (mounted.current) setRepos(list)
    } catch (err) {
      if (mounted.current) setReposError(errorMessage(err))
    }
  }, [])

  const startDeviceFlow = useCallback(async () => {
    stopPolling()
    setState({ phase: 'requesting' })
    try {
      const res = await api.requestGithubDeviceCode()
      if (!mounted.current) return
      setState({ phase: 'waiting', userCode: res.user_code, verificationUri: res.verification_uri })
      window.open(res.verification_uri, '_blank', 'noopener')
      const delay = Math.max(5, res.interval || 5) * 1000
      pollRef.current = window.setInterval(async () => {
        try {
          const poll = await api.pollGithubDeviceToken({ device_code: res.device_code })
          if (!mounted.current) return
          if (poll.access_token) {
            stopPolling()
            setToken(poll.access_token)
            setState({ phase: 'authorized', source: 'device' })
            void loadRepos(poll.access_token)
          } else if (poll.error && poll.error !== 'authorization_pending' && poll.error !== 'slow_down') {
            stopPolling()
            setState({ phase: 'error', message: poll.error_description || poll.error })
          }
        } catch (err) {
          stopPolling()
          if (mounted.current) setState({ phase: 'error', message: errorMessage(err) })
        }
      }, delay)
    } catch (err) {
      if (mounted.current) setState({ phase: 'error', message: errorMessage(err) })
    }
  }, [loadRepos, stopPolling])

  const usePastedToken = useCallback(
    (value: string) => {
      setToken(value)
      if (value.trim()) {
        setState({ phase: 'authorized', source: 'token' })
        void loadRepos(value.trim())
      }
    },
    [loadRepos],
  )

  const cancel = useCallback(() => {
    stopPolling()
    setState({ phase: 'idle' })
  }, [stopPolling])

  return { state, token, repos, reposError, startDeviceFlow, usePastedToken, loadRepos, cancel }
}
