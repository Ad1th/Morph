import { useRef, useState, type ChangeEvent } from 'react'
import type { OsName } from '../theme/useOsTheme'
import './Desktop.css'

const TAGLINE = 'The quieter you become, the more you are able to hear'

type DialogView = 'choose' | 'github' | 'done'

export function Desktop({
  os,
  onStart,
  onExperiment,
}: {
  os: OsName
  onStart: () => void
  onExperiment: () => void
}) {
  const [open, setOpen] = useState(true)
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
      <FolderGlyph os={os} onClick={() => setOpen(true)} />

      <div className="desktop__center">
        <h1 className="desktop__wordmark">MORPH</h1>
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
              onClick={() => setOpen(false)}
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
                <button className="desktop__btn bevel-raised" onClick={onExperiment}>
                  Run experiment
                </button>
                <button className="desktop__btn desktop__btn--primary bevel-raised" onClick={onStart}>
                  Run once
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

function FolderGlyph({ os, onClick }: { os: OsName; onClick: () => void }) {
  if (os === 'windows') {
    return (
      <div className="desktop__folder desktop__folder--win98" title="Upload Project" onClick={onClick}>
        <div className="desktop__folder-tab" />
        <div className="desktop__folder-body">
          <div className="desktop__folder-highlight" />
        </div>
      </div>
    )
  }
  const color = os === 'mac' ? '#5aa7f5' : '#4a8fd6'
  return (
    <svg
      className="desktop__folder"
      width="44"
      height="36"
      viewBox="0 0 44 36"
      aria-hidden
      onClick={onClick}
      style={{ cursor: 'pointer' }}
    >
      <path d="M2 6a2 2 0 0 1 2-2h12l4 4h20a2 2 0 0 1 2 2v22a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6z" fill={color} />
    </svg>
  )
}
