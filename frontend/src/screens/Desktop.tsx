import type { OsName } from '../theme/useOsTheme'
import './Desktop.css'

const TAGLINE = 'The quieter you become, the more you are able to hear'

export function Desktop({ os, onStart }: { os: OsName; onStart: () => void }) {
  return (
    <div className="desktop" data-os={os}>
      <FolderGlyph os={os} />

      <div className="desktop__center">
        <h1 className="desktop__wordmark">MORPH</h1>
        <p className="desktop__tagline">&ldquo;{TAGLINE}&rdquo;</p>
      </div>

      <div className="desktop__dialog">
        <div className="desktop__dialog-titlebar">
          {os === 'mac' && (
            <span className="desktop__traffic-lights">
              <i />
              <i />
              <i />
            </span>
          )}
          <span className="desktop__dialog-title">
            {os === 'linux' ? '$ upload-project --v1' : 'Upload Project - v1.0'}
          </span>
          {os === 'windows' && <span className="desktop__dialog-close">×</span>}
        </div>
        <div className="desktop__dialog-body">
          <p>Connect to/upload your project.</p>
          <div className="desktop__dialog-actions">
            <button
              className="desktop__btn"
              title="GitHub integration is coming soon"
              disabled
            >
              Connect through GitHub
            </button>
            <button className="desktop__btn desktop__btn--primary" onClick={onStart}>
              Upload Project
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function FolderGlyph({ os }: { os: OsName }) {
  const color = os === 'windows' ? '#f3d54e' : os === 'mac' ? '#5aa7f5' : '#4a8fd6'
  return (
    <svg className="desktop__folder" width="44" height="36" viewBox="0 0 44 36" aria-hidden>
      <path d="M2 6a2 2 0 0 1 2-2h12l4 4h20a2 2 0 0 1 2 2v22a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6z" fill={color} />
    </svg>
  )
}
