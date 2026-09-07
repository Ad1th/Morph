import type { OsName } from '../theme/useOsTheme'
import './DesktopCorners.css'

/**
 * The project folder icon, top-left of the desktop.
 *
 * It lives here rather than inside a screen because it is desktop furniture in
 * every mockup: visible behind the upload dialog and behind the parameter
 * window alike. The top-right corner belongs to <OsSwitcher>, which is the
 * badge that opens the environment menu.
 */
export function DesktopCorners({ os, onFolderClick }: { os: OsName; onFolderClick: () => void }) {
  return (
    <div className="corners" data-os={os}>
      <button
        type="button"
        className="corners__slot corners__slot--left"
        onClick={onFolderClick}
        title="Project"
      >
        <FolderGlyph os={os} />
        <span className="corners__label">Project</span>
      </button>
    </div>
  )
}

function FolderGlyph({ os }: { os: OsName }) {
  if (os === 'windows') {
    return (
      <span className="corners__glyph corners__folder--win98" aria-hidden>
        <span className="corners__folder-tab" />
        <span className="corners__folder-body">
          <span className="corners__folder-highlight" />
        </span>
      </span>
    )
  }

  const color = os === 'mac' ? '#5aa7f5' : '#4a8fd6'
  return (
    <svg className="corners__glyph" viewBox="0 0 44 36" aria-hidden>
      <path
        d="M2 6a2 2 0 0 1 2-2h12l4 4h20a2 2 0 0 1 2 2v22a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6z"
        fill={color}
      />
    </svg>
  )
}
