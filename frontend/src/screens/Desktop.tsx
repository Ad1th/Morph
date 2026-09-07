import { useRef, useState, type ChangeEvent } from 'react'
import { api } from '../api/client'
import type { ProjectInfo } from '../api/types'
import type { OsName } from '../theme/useOsTheme'
import './Desktop.css'

const TAGLINE = 'Now it breaks on your machine too'

type DialogView = 'choose' | 'github' | 'local' | 'busy' | 'done'

export function Desktop({
  os,
  open,
  onOpenChange,
  onProject,
  onStart,
}: {
  os: OsName
  /** Controlled by App so the desktop folder icon can reopen this dialog from
      any screen, not just when the desktop happens to be mounted. */
  open: boolean
  onOpenChange: (open: boolean) => void
  onProject: (project: ProjectInfo | null) => void
  onStart: () => void
}) {
  const [view, setView] = useState<DialogView>('choose')
  const [repo, setRepo] = useState('')
  const [token, setToken] = useState(() => localStorage.getItem('morph_github_token') || '')
  const [branch, setBranch] = useState('')
  const [authMethod, setAuthMethod] = useState<'interactive' | 'token'>('token')
  const [clientId, setClientId] = useState('')
  const [userRepos, setUserRepos] = useState<
    Array<{ full_name: string; name: string; default_branch: string; private: boolean }>
  >([])
  const [deviceCode, setDeviceCode] = useState<{
    device_code: string
    user_code: string
    verification_uri: string
    interval: number
  } | null>(null)
  const [isAuthorizing, setIsAuthorizing] = useState(false)
  const [authStatus, setAuthStatus] = useState('')
  const [localPath, setLocalPath] = useState('apps/timeout')
  const [note, setNote] = useState('')
  const [project, setProject] = useState<ProjectInfo | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const folderRef = useRef<HTMLInputElement>(null)
  const pollIntervalRef = useRef<number | null>(null)

  async function startDeviceFlow() {
    setIsAuthorizing(true)
    setAuthStatus('Requesting device code from GitHub…')
    try {
      const res = await api.requestGithubDeviceCode({
        client_id: clientId.trim() || undefined,
      })
      setDeviceCode(res)
      setAuthStatus('Waiting for authorization on GitHub…')

      // Open GitHub device authorization page
      window.open(res.verification_uri, '_blank')
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(res.user_code).catch(() => {})
      }

      // Start polling
      const pollDelay = (res.interval || 5) * 1000
      pollIntervalRef.current = window.setInterval(async () => {
        try {
          const pollRes = await api.pollGithubDeviceToken({
            device_code: res.device_code,
            client_id: clientId.trim() || undefined,
          })
          if (pollRes.access_token) {
            clearInterval(pollIntervalRef.current!)
            setToken(pollRes.access_token)
            localStorage.setItem('morph_github_token', pollRes.access_token)
            setIsAuthorizing(false)
            setDeviceCode(null)
            setAuthStatus('Authorized successfully!')
            void loadUserRepos(pollRes.access_token)
          } else if (pollRes.error === 'authorization_pending') {
            setAuthStatus('Waiting for authorization on GitHub…')
          } else if (pollRes.error === 'slow_down') {
            setAuthStatus('Polling throttled by GitHub, still waiting…')
          } else if (pollRes.error) {
            clearInterval(pollIntervalRef.current!)
            setIsAuthorizing(false)
            setAuthStatus(`Authorization failed: ${pollRes.error_description || pollRes.error}`)
          }
        } catch (err) {
          clearInterval(pollIntervalRef.current!)
          setIsAuthorizing(false)
          setAuthStatus(`Polling error: ${err instanceof Error ? err.message : String(err)}`)
        }
      }, pollDelay)
    } catch (err) {
      setIsAuthorizing(false)
      setAuthStatus(`Error starting flow: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  async function loadUserRepos(authToken: string) {
    if (!authToken.trim()) return
    try {
      const repos = await api.fetchGithubRepos(authToken.trim())
      setUserRepos(repos)
      if (repos.length > 0 && !repo) {
        setRepo(repos[0].full_name)
        setBranch(repos[0].default_branch || 'main')
      }
    } catch {
      // Ignore repos fetch error and allow manual entry
    }
  }

  function handleConnect() {
    const trimmed = repo.trim()
    if (!trimmed) {
      setNote('Enter a repository URL first.')
      setView('done')
      return
    }
    void load(`Cloning and authorising ${trimmed}…`, () =>
      api.useGithubProject({
        repo: trimmed,
        token: token.trim() || undefined,
        branch: branch.trim() || undefined,
      }),
    )
  }

  /** Shared by both upload paths and the local-directory path: one place that
      owns the busy state and surfaces the real backend error message. */
  async function load(pending: string, fn: () => Promise<ProjectInfo>) {
    setNote(pending)
    setView('busy')
    try {
      const info = await fn()
      setProject(info)
      onProject(info)
      setNote(`${info.name}: ${info.file_count} file${info.file_count === 1 ? '' : 's'} ready.`)
    } catch (err) {
      setProject(null)
      onProject(null)
      setNote(err instanceof Error ? err.message : String(err))
    }
    setView('done')
  }

  function handleFiles(e: ChangeEvent<HTMLInputElement>) {
    // Copy before clearing: `files` is a live view of the input, and resetting
    // value (so the same folder can be picked twice in a row) empties it.
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (files.length === 0) {
      setNote('No files selected.')
      setView('done')
      return
    }
    void load(`Uploading ${files.length} file${files.length === 1 ? '' : 's'}…`, () =>
      api.uploadProject(files),
    )
  }

  const message =
    view === 'choose'
      ? 'Connect/upload your project.'
      : view === 'github'
        ? 'Connect and authorise your GitHub repository.'
        : view === 'local'
          ? 'Point Morph at a directory on this machine.'
          : note

  return (
    <div className="desktop" data-os={os}>
      {/* The folder and badge icons are rendered once by <DesktopCorners> in
          App, so that they stay aligned across every screen. */}
      <div className="desktop__center">
        <h1 className="desktop__wordmark">MORPH</h1>
        {/* Rendered in every skin but only visible on Windows. Keeping the
            element in the layout holds the block's height constant, so the
            wordmark sits at the same spot whichever skin is on screen; the
            CSS hides it rather than React dropping it. */}
        <p className="desktop__tagline">&ldquo;{TAGLINE}&rdquo;</p>
      </div>

      {open && (
        <div className="desktop__dialog bevel-raised">
          <div className="desktop__dialog-titlebar">
            {os === 'mac' && (
              <span className="desktop__traffic-lights">
                <i />
                <i />
                <i />
              </span>
            )}
            <span className="desktop__dialog-title">
              {os === 'linux' ? '$ upload-project --v1' : 'Upload Project – v1.0'}
            </span>
            <button
              className="desktop__dialog-close bevel-raised"
              onClick={() => onOpenChange(false)}
              aria-label="Close"
            >
              ×
            </button>
          </div>
          <div className="desktop__dialog-body">
            <div className="desktop__dialog-row">
              <span className="desktop__dialog-icon bevel-sunken" aria-hidden>
                <span className="desktop__dialog-icon-inner" />
              </span>
              <p className="desktop__dialog-message" aria-live="polite">
                {message}
              </p>
            </div>

            {view === 'choose' && (
              <>
                <div className="desktop__dialog-actions">
                  <button className="desktop__btn bevel-raised" onClick={() => setView('github')}>
                    Connect through GitHub
                  </button>
                  <button
                    className="desktop__btn bevel-raised"
                    onClick={() => folderRef.current?.click()}
                  >
                    Upload Folder
                  </button>
                </div>
                <div className="desktop__dialog-actions">
                  <button
                    className="desktop__btn bevel-raised"
                    onClick={() => fileRef.current?.click()}
                  >
                    Upload Files
                  </button>
                  <button className="desktop__btn bevel-raised" onClick={() => setView('local')}>
                    Use Local Folder
                  </button>
                </div>
              </>
            )}

            {view === 'github' && (
              <div className="desktop__github">
                <div className="desktop__tabs">
                  <button
                    type="button"
                    className={`desktop__btn bevel-raised desktop__tab ${
                      authMethod === 'token' ? 'desktop__tab--active' : ''
                    }`}
                    onClick={() => setAuthMethod('token')}
                  >
                    Token / Repository URL
                  </button>
                  <button
                    type="button"
                    className={`desktop__btn bevel-raised desktop__tab ${
                      authMethod === 'interactive' ? 'desktop__tab--active' : ''
                    }`}
                    onClick={() => setAuthMethod('interactive')}
                  >
                    Interactive GitHub Login
                  </button>
                </div>

                {authMethod === 'interactive' ? (
                  <div>
                    {!deviceCode && !token && (
                      <div>
                        <div className="desktop__field">
                          <label htmlFor="client-id" className="desktop__label">
                            OAuth Client ID (optional if set in env)
                          </label>
                          <input
                            id="client-id"
                            className="desktop__input bevel-sunken"
                            value={clientId}
                            onChange={(e) => setClientId(e.target.value)}
                            placeholder="Optional GitHub OAuth App Client ID"
                          />
                        </div>
                        <div className="desktop__dialog-actions">
                          <button
                            type="button"
                            className="desktop__btn bevel-raised"
                            disabled={isAuthorizing}
                            onClick={() => void startDeviceFlow()}
                          >
                            {isAuthorizing ? 'Starting…' : 'Start GitHub Authorization'}
                          </button>
                        </div>
                      </div>
                    )}

                    {deviceCode && (
                      <div className="desktop__device-box bevel-sunken">
                        <p className="desktop__label">Enter this code on GitHub:</p>
                        <div className="desktop__device-code">{deviceCode.user_code}</div>
                        <p className="desktop__label" style={{ fontSize: '11px', marginTop: 4 }}>
                          Code copied to clipboard. Opening authorization window…
                        </p>
                        <button
                          type="button"
                          className="desktop__btn bevel-raised"
                          style={{ marginTop: 8 }}
                          onClick={() => {
                            window.open(deviceCode.verification_uri, '_blank')
                            if (navigator.clipboard) {
                              void navigator.clipboard.writeText(deviceCode.user_code)
                            }
                          }}
                        >
                          Reopen GitHub Device Page
                        </button>
                      </div>
                    )}

                    {authStatus && (
                      <p className="desktop__label" style={{ textAlign: 'center', marginTop: 6 }}>
                        {authStatus}
                      </p>
                    )}
                  </div>
                ) : (
                  <div>
                    <div className="desktop__field">
                      <label htmlFor="token" className="desktop__label">
                        GitHub Personal Access Token (PAT)
                      </label>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <input
                          id="token"
                          type="password"
                          className="desktop__input bevel-sunken"
                          value={token}
                          onChange={(e) => {
                            setToken(e.target.value)
                            localStorage.setItem('morph_github_token', e.target.value)
                          }}
                          placeholder="ghp_... or Personal Access Token"
                          autoComplete="off"
                        />
                        <button
                          type="button"
                          className="desktop__btn bevel-raised"
                          style={{ flex: 'none', padding: '0 10px' }}
                          disabled={!token.trim()}
                          onClick={() => void loadUserRepos(token)}
                        >
                          Fetch Repos
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {userRepos.length > 0 && (
                  <div className="desktop__field">
                    <label htmlFor="repo-select" className="desktop__label">
                      Select from your repositories ({userRepos.length})
                    </label>
                    <select
                      id="repo-select"
                      className="desktop__select bevel-sunken"
                      value={repo}
                      onChange={(e) => {
                        const selected = userRepos.find((r) => r.full_name === e.target.value)
                        if (selected) {
                          setRepo(selected.full_name)
                          setBranch(selected.default_branch || 'main')
                        } else {
                          setRepo(e.target.value)
                        }
                      }}
                    >
                      <option value="">-- Choose a repository --</option>
                      {userRepos.map((r) => (
                        <option key={r.full_name} value={r.full_name}>
                          {r.full_name} {r.private ? '🔒' : '🌐'}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div className="desktop__field">
                  <label htmlFor="repo" className="desktop__label">
                    Repository URL or owner/repo
                  </label>
                  <input
                    id="repo"
                    className="desktop__input bevel-sunken"
                    value={repo}
                    onChange={(e) => setRepo(e.target.value)}
                    placeholder="e.g. Ad1th/Morph or https://github.com/Ad1th/Morph"
                  />
                </div>

                <div className="desktop__field">
                  <label htmlFor="branch" className="desktop__label">
                    Branch / Tag (optional)
                  </label>
                  <input
                    id="branch"
                    className="desktop__input bevel-sunken"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    placeholder="main / master (default)"
                  />
                </div>

                <div className="desktop__dialog-actions">
                  <button className="desktop__btn bevel-raised" onClick={() => setView('choose')}>
                    Back
                  </button>
                  <button
                    className="desktop__btn desktop__btn--primary bevel-raised"
                    disabled={repo.trim() === ''}
                    onClick={handleConnect}
                  >
                    Connect &amp; Authorise
                  </button>
                </div>
              </div>
            )}

            {view === 'local' && (
              <div className="desktop__github">
                <label htmlFor="local-path" className="desktop__label">
                  Directory path (absolute, or relative to the Morph repo)
                </label>
                <input
                  id="local-path"
                  className="desktop__input bevel-sunken"
                  value={localPath}
                  onChange={(e) => setLocalPath(e.target.value)}
                  placeholder="apps/timeout"
                />
                <div className="desktop__dialog-actions">
                  <button className="desktop__btn bevel-raised" onClick={() => setView('choose')}>
                    Back
                  </button>
                  <button
                    className="desktop__btn bevel-raised"
                    disabled={localPath.trim() === ''}
                    onClick={() =>
                      void load('Opening directory…', () => api.useLocalProject(localPath.trim()))
                    }
                  >
                    Use Directory
                  </button>
                </div>
              </div>
            )}

            {view === 'done' && (
              <>
                {project?.suggested_command && (
                  <p className="desktop__label">Detected: {project.suggested_command}</p>
                )}
                <div className="desktop__dialog-actions">
                  <button className="desktop__btn bevel-raised" onClick={() => setView('choose')}>
                    Back
                  </button>
                  <button
                    className="desktop__btn desktop__btn--primary bevel-raised"
                    onClick={onStart}
                  >
                    OK
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      <input
        ref={fileRef}
        type="file"
        multiple
        onChange={handleFiles}
        style={{ display: 'none' }}
      />
      {/* webkitdirectory is a real attribute on every browser that matters but
          is absent from React's typed input props, hence the cast. */}
      <input
        ref={folderRef}
        type="file"
        multiple
        onChange={handleFiles}
        style={{ display: 'none' }}
        {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
      />
    </div>
  )
}
