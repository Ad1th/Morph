import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react'
import { api, errorMessage } from '../api/client'
import type { ProjectInfo } from '../api/types'
import { useGithubAuth } from '../hooks/useGithubAuth'
import { fmtDate, plural } from '../lib/format'
import type { ScreenId } from '../routes'
import { useRunDraft } from '../state/useRunDraft'
import { Chip } from '../components/ui/Chips'
import { Dialog } from '../components/ui/Dialog'
import { Icon } from '../components/ui/Icon'
import './screens.css'

type Busy = { label: string } | null

export function Projects({ onNavigate }: { onNavigate: (s: ScreenId) => void }) {
  const { draft, setProject } = useRunDraft()
  const [recent, setRecent] = useState<ProjectInfo[] | null>(null)
  const [recentError, setRecentError] = useState<string | null>(null)
  const [busy, setBusy] = useState<Busy>(null)
  const [error, setError] = useState<string | null>(null)
  const [localPath, setLocalPath] = useState('apps/pool_retry')
  const [install, setInstall] = useState(false)
  const [githubOpen, setGithubOpen] = useState(false)
  const folderRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(() => {
    api
      .listProjects()
      .then((list) => {
        setRecent([...list].reverse())
        setRecentError(null)
      })
      .catch((err) => setRecentError(errorMessage(err)))
  }, [])

  useEffect(refresh, [refresh])

  async function connect(label: string, fn: () => Promise<ProjectInfo>) {
    setBusy({ label })
    setError(null)
    try {
      let info = await fn()
      if (install && info.project_id) {
        setBusy({ label: `Installing dependencies for ${info.name}` })
        info = await api.installProject(info.project_id)
      }
      setProject(info)
      refresh()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  function onFolder(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (files.length === 0) return
    void connect(`Uploading ${plural(files.length, 'file')}`, () => api.uploadProject(files))
  }

  async function installNow(p: ProjectInfo) {
    setBusy({ label: `Installing dependencies for ${p.name}` })
    setError(null)
    try {
      const info = await api.installProject(p.project_id)
      setProject(info)
      refresh()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  async function forget(p: ProjectInfo) {
    try {
      await api.deleteProject(p.project_id)
      if (draft.project?.project_id === p.project_id) setProject(null)
      refresh()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const project = draft.project

  return (
    <>
      <header className="page__head">
        <div>
          <h1>Projects</h1>
          <p>Point Morph at the code that misbehaves. It detects the test command; you can change it on the Run screen.</p>
        </div>
      </header>

      {project && (
        <section className="card card--tint project-current reveal" aria-live="polite">
          <div className="project-current__main">
            <div className="row">
              <Icon name="folder" size={16} />
              <strong>{project.name}</strong>
              <Chip>{project.source ?? 'local'}</Chip>
              {project.repo && <Chip icon="github">{project.repo}{project.branch ? `@${project.branch}` : ''}</Chip>}
              {project.venv && <Chip tone="ok" icon="check">deps installed</Chip>}
              {project.deps_failed.length > 0 && (
                <Chip tone="warn" icon="alert">
                  {plural(project.deps_failed.length, 'install step')} failed
                </Chip>
              )}
            </div>
            <p className="small muted project-current__path">{project.path}</p>
            <p className="small">
              {project.suggested_command ? (
                <>
                  Detected command <code className="inline-code">{project.suggested_command}</code>
                </>
              ) : (
                <span className="muted">No entry point detected. Type the command on the Run screen.</span>
              )}
            </p>
            {project.deps_failed.length > 0 && (
              <ul className="small muted project-current__fails">
                {project.deps_failed.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="page__actions">
            {!project.venv && (
              <button className="btn" onClick={() => installNow(project)} disabled={busy != null}>
                <Icon name="refresh" size={14} />
                {project.deps_failed.length ? 'Retry install' : 'Install dependencies'}
              </button>
            )}
            <button className="btn btn--primary" onClick={() => onNavigate('run')}>
              <Icon name="play" size={14} />
              Set up a run
            </button>
          </div>
        </section>
      )}

      {busy && (
        <p className="note" role="status" aria-live="polite">
          <Icon name="refresh" />
          {busy.label}…
        </p>
      )}
      {error && (
        <p className="note" data-tone="fail" role="alert">
          <Icon name="alert" />
          <span>{error}</span>
        </p>
      )}

      <section className="section">
        <div className="section__head">
          <h2>Connect a project</h2>
        </div>
        <div className="connect-grid">
          <form
            className="connect-card"
            onSubmit={(e) => {
              e.preventDefault()
              if (localPath.trim()) void connect(`Reading ${localPath.trim()}`, () => api.useLocalProject(localPath.trim()))
            }}
          >
            <h3>
              <Icon name="terminal" size={14} /> Local folder
            </h3>
            <p className="small muted">A path on this machine. Relative paths resolve from the Morph repo root.</p>
            <div className="field">
              <label htmlFor="local-path">Path</label>
              <input
                id="local-path"
                className="input"
                value={localPath}
                onChange={(e) => setLocalPath(e.target.value)}
                placeholder="apps/pool_retry or /Users/you/service"
                spellCheck={false}
              />
            </div>
            <button className="btn" type="submit" disabled={busy != null || !localPath.trim()}>
              Use this folder
            </button>
          </form>

          <div className="connect-card">
            <h3>
              <Icon name="github" size={14} /> GitHub
            </h3>
            <p className="small muted">Clone a repository. Public repos need no token; private ones use the device flow or a token you paste.</p>
            <button className="btn" onClick={() => setGithubOpen(true)} disabled={busy != null}>
              Connect through GitHub
            </button>
          </div>

          <div className="connect-card">
            <h3>
              <Icon name="upload" size={14} /> Upload
            </h3>
            <p className="small muted">Send a folder from this browser. Skips node_modules, .git and virtualenvs; 50 MB limit.</p>
            <input
              ref={folderRef}
              type="file"
              className="sr-only"
              onChange={onFolder}
              aria-label="Choose a project folder"
              // @ts-expect-error non-standard, widely supported
              webkitdirectory=""
              multiple
            />
            <button className="btn" onClick={() => folderRef.current?.click()} disabled={busy != null}>
              Choose a folder
            </button>
          </div>
        </div>
        <label className="toggle connect-install">
          <input type="checkbox" checked={install} onChange={(e) => setInstall(e.target.checked)} />
          <span className="small">Install dependencies into an isolated environment after connecting</span>
        </label>
      </section>

      <section className="section">
        <div className="section__head">
          <h2>Recent</h2>
          <button className="btn btn--ghost btn--sm" onClick={refresh}>
            <Icon name="refresh" size={13} /> Refresh
          </button>
        </div>
        {recentError && (
          <p className="note" data-tone="warn">
            <Icon name="alert" />
            <span>{recentError}</span>
          </p>
        )}
        {recent && recent.length === 0 && <p className="muted small">Nothing connected yet.</p>}
        {recent && recent.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Source</th>
                  <th>Command</th>
                  <th>Connected</th>
                  <th className="num">Files</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {recent.map((p) => (
                  <tr key={p.project_id} data-active={draft.project?.project_id === p.project_id}>
                    <td>
                      <strong>{p.name}</strong>
                      <div className="faint small project-path">{p.path}</div>
                    </td>
                    <td>{p.source ?? 'local'}{p.repo ? ` · ${p.repo}` : ''}</td>
                    <td>
                      <code className="inline-code">{p.suggested_command ?? '—'}</code>
                    </td>
                    <td className="muted">{fmtDate(p.created_at)}</td>
                    <td className="num">{p.file_count}</td>
                    <td>
                      <div className="row" style={{ justifyContent: 'flex-end' }}>
                        <button className="btn btn--sm" onClick={() => setProject(p)} disabled={busy != null}>
                          Use
                        </button>
                        <button className="btn btn--ghost btn--icon btn--sm" onClick={() => forget(p)} aria-label={`Forget ${p.name}`}>
                          <Icon name="trash" size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <GithubDialog
        open={githubOpen}
        onClose={() => setGithubOpen(false)}
        busy={busy != null}
        onConnect={(repo, branch, token) => {
          setGithubOpen(false)
          void connect(`Cloning ${repo}`, () => api.useGithubProject({ repo, branch: branch || undefined, token: token || undefined, install }))
        }}
      />
    </>
  )
}

function GithubDialog({
  open,
  onClose,
  busy,
  onConnect,
}: {
  open: boolean
  onClose: () => void
  busy: boolean
  onConnect: (repo: string, branch: string, token: string) => void
}) {
  const gh = useGithubAuth()
  const [repo, setRepo] = useState('')
  const [branch, setBranch] = useState('')
  const [pasted, setPasted] = useState('')

  const canConnect = repo.trim().length > 0 && !busy

  return (
    <Dialog open={open} onClose={onClose} title="Connect through GitHub">
      <div className="stack">
        {gh.state.phase === 'server' && (
          <p className="note" data-tone="ok">
            <Icon name="check" />
            <span>
              This machine is already signed in ({gh.state.source}). Private repositories will clone without a token.
            </span>
          </p>
        )}
        {gh.state.phase === 'waiting' && (
          <p className="note" role="status">
            <Icon name="github" />
            <span>
              Enter code <strong className="ghcode">{gh.state.userCode}</strong> at{' '}
              <a href={gh.state.verificationUri} target="_blank" rel="noreferrer">
                {gh.state.verificationUri}
              </a>
              . Waiting for approval…
            </span>
          </p>
        )}
        {gh.state.phase === 'authorized' && (
          <p className="note" data-tone="ok">
            <Icon name="check" />
            <span>Authorized. The token stays in this tab only.</span>
          </p>
        )}
        {gh.state.phase === 'error' && (
          <p className="note" data-tone="fail" role="alert">
            <Icon name="alert" />
            <span>{gh.state.message}</span>
          </p>
        )}

        <div className="row">
          {gh.state.phase !== 'authorized' && gh.state.phase !== 'server' && (
            <button className="btn" onClick={gh.startDeviceFlow} disabled={gh.state.phase === 'waiting' || gh.state.phase === 'requesting'}>
              <Icon name="github" size={14} />
              {gh.state.phase === 'waiting' ? 'Waiting for GitHub' : 'Sign in with a device code'}
            </button>
          )}
          {gh.state.phase === 'waiting' && (
            <button className="btn btn--ghost" onClick={gh.cancel}>
              Cancel
            </button>
          )}
          {gh.state.phase === 'server' && (
            <button className="btn btn--sm" onClick={() => gh.loadRepos()}>
              List my repositories
            </button>
          )}
        </div>

        <div className="field">
          <label htmlFor="gh-token">Personal access token (optional, not stored)</label>
          <input
            id="gh-token"
            className="input"
            type="password"
            autoComplete="off"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            onBlur={() => gh.usePastedToken(pasted)}
            placeholder="ghp_…"
          />
        </div>

        {gh.repos.length > 0 && (
          <div className="field">
            <label htmlFor="gh-repo-list">Your repositories</label>
            <select
              id="gh-repo-list"
              className="select"
              value={gh.repos.some((r) => r.full_name === repo) ? repo : ''}
              onChange={(e) => {
                const r = gh.repos.find((x) => x.full_name === e.target.value)
                if (r) {
                  setRepo(r.full_name)
                  setBranch(r.default_branch)
                }
              }}
            >
              <option value="">Choose…</option>
              {gh.repos.map((r) => (
                <option key={r.full_name} value={r.full_name}>
                  {r.full_name}
                  {r.private ? ' (private)' : ''}
                </option>
              ))}
            </select>
          </div>
        )}
        {gh.reposError && <p className="field__error">{gh.reposError}</p>}

        <div className="field">
          <label htmlFor="gh-repo">Repository</label>
          <input
            id="gh-repo"
            className="input"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            placeholder="owner/repo or https://github.com/owner/repo"
            spellCheck={false}
          />
        </div>
        <div className="field">
          <label htmlFor="gh-branch">Branch (optional)</label>
          <input id="gh-branch" className="input" value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" />
        </div>

        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn--primary" disabled={!canConnect} onClick={() => onConnect(repo.trim(), branch.trim(), gh.token || pasted.trim())}>
            Clone and connect
          </button>
        </div>
      </div>
    </Dialog>
  )
}
