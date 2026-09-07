import { useEffect, useState } from 'react'
import { api } from './api/client'
import { Rail } from './components/Rail'
import { TargetSelect } from './components/TargetSelect'
import { Icon } from './components/ui/Icon'
import { SCREENS, useRoute } from './routes'
import { Environment } from './screens/Environment'
import { Experiment } from './screens/Experiment'
import { Projects } from './screens/Projects'
import { Regressions } from './screens/Regressions'
import { Run } from './screens/Run'
import { Threshold } from './screens/Threshold'
import { setState, useStore } from './state/store'
import './components/shell.css'

export default function App() {
  const { screen, navigate } = useRoute()
  const theme = useStore((s) => s.theme)
  const project = useStore((s) => s.draft.project)
  const [server, setServer] = useState<'checking' | 'ok' | 'down'>('checking')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    let alive = true
    const check = () =>
      api
        .health()
        .then(() => alive && setServer('ok'))
        .catch(() => alive && setServer('down'))
    void check()
    const t = window.setInterval(check, 15000)
    return () => {
      alive = false
      window.clearInterval(t)
    }
  }, [])

  const meta = SCREENS.find((s) => s.id === screen)!

  return (
    <div className="shell">
      <Rail active={screen} onNavigate={navigate} />
      <div className="shell__main">
        <header className="topbar">
          <div className="topbar__crumb">
            <span className="muted">{meta.label}</span>
            {project && (
              <>
                <span className="faint" aria-hidden>
                  /
                </span>
                <button className="topbar__project" onClick={() => navigate('projects')} title={project.path}>
                  <Icon name="folder" size={13} />
                  {project.name}
                </button>
              </>
            )}
          </div>
          <div className="topbar__tools">
            <span
              className="topbar__server"
              data-state={server}
              role="status"
              title={server === 'ok' ? 'Morph server reachable' : server === 'down' ? 'Morph server not reachable' : 'Checking server'}
            >
              <Icon name="dot" size={10} />
              {server === 'ok' ? 'server' : server === 'down' ? 'server down' : 'checking'}
            </span>
            <TargetSelect />
            <button
              className="btn btn--ghost btn--icon"
              onClick={() => setState({ theme: theme === 'dark' ? 'light' : 'dark' })}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
            </button>
          </div>
        </header>

        <main className="content" id="main" key={screen}>
          {screen === 'projects' && <Projects onNavigate={navigate} />}
          {screen === 'run' && <Run onNavigate={navigate} />}
          {screen === 'experiment' && <Experiment onNavigate={navigate} />}
          {screen === 'threshold' && <Threshold onNavigate={navigate} />}
          {screen === 'regressions' && <Regressions onNavigate={navigate} />}
          {screen === 'environment' && <Environment onNavigate={navigate} />}
        </main>
      </div>
    </div>
  )
}
