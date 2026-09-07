import { useRef, useState, type ChangeEvent } from 'react'
import type { OsName } from '../theme/useOsTheme'
import './Desktop.css'

const TAGLINE = 'Now it breaks on your machine too'

type DialogView = 'choose' | 'github' | 'done'

export function Desktop({
  os,
  open,
  onOpenChange,
  onStart,
}: {
  os: OsName
  /** Controlled by App so the desktop folder icon can reopen this dialog from
      any screen, not just when the desktop happens to be mounted. */
  open: boolean
  onOpenChange: (open: boolean) => void
  onStart: () => void
}) {
  const [view, setView] = useState<DialogView>('choose')
  const [repo, setRepo] = useState('')
  const [note, setNote] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  function handleConnect() {
    const trimmed = repo.trim()
    setNote(trimmed ? `Connected to ${trimmed}` : 'Enter a repository URL first.')
    setView('done')
  }

  function handleFiles(e: ChangeEvent<HTMLInputElement>) {
    const n = e.target.files?.length ?? 0
    setNote(n ? `${n} file${n === 1 ? '' : 's'} uploaded.` : 'No files selected.')
    setView('done')
  }

  const message =
    view === 'choose' ? 'Connect/upload your project.' : view === 'github' ? 'Paste your repository URL.' : note

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
              <p className="desktop__dialog-message">{message}</p>
            </div>

            {view === 'choose' && (
              <div className="desktop__dialog-actions">
                <button className="desktop__btn bevel-raised" onClick={() => setView('github')}>
                  Connect through GitHub
                </button>
                <button
                  className="desktop__btn bevel-raised"
                  onClick={() => fileRef.current?.click()}
                >
                  Upload Project
                </button>
              </div>
            )}

            {view === 'github' && (
              <div className="desktop__github">
                <label htmlFor="repo" className="desktop__label">
                  Repository URL
                </label>
                <input
                  id="repo"
                  className="desktop__input bevel-sunken"
                  value={repo}
                  onChange={(e) => setRepo(e.target.value)}
                  placeholder="github.com/user/project"
                />
                <div className="desktop__dialog-actions">
                  <button className="desktop__btn bevel-raised" onClick={() => setView('choose')}>
                    Back
                  </button>
                  <button className="desktop__btn bevel-raised" onClick={handleConnect}>
                    Connect
                  </button>
                </div>
              </div>
            )}

            {view === 'done' && (
              <div className="desktop__dialog-actions">
                <button className="desktop__btn bevel-raised" onClick={() => setView('choose')}>
                  Back
                </button>
                <button className="desktop__btn desktop__btn--primary bevel-raised" onClick={onStart}>
                  OK
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <input ref={fileRef} type="file" multiple onChange={handleFiles} style={{ display: 'none' }} />
    </div>
  )
}
