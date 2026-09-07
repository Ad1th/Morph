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
  const [token, setToken] = useState('')
  const [branch, setBranch] = useState('')
  const [localPath, setLocalPath] = useState('apps/timeout')
  const [note, setNote] = useState('')
  const [project, setProject] = useState<ProjectInfo | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const folderRef = useRef<HTMLInputElement>(null)

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
                <div className="desktop__field">
                  <label htmlFor="repo" className="desktop__label">
                    Repository (owner/repo or URL)
                  </label>
                  <input
                    id="repo"
                    className="desktop__input bevel-sunken"
                    value={repo}
                    onChange={(e) => setRepo(e.target.value)}
                    placeholder="github.com/user/project or user/project"
                  />
                </div>
                <div className="desktop__field">
                  <label htmlFor="token" className="desktop__label">
                    GitHub Token / PAT (optional for public, required for private)
                  </label>
                  <input
                    id="token"
                    type="password"
                    className="desktop__input bevel-sunken"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="ghp_... or Personal Access Token"
                    autoComplete="off"
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
                    className="desktop__btn bevel-raised"
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
