import { useState } from 'react'
import { DesktopCorners } from './components/DesktopCorners'
import { OsSwitcher } from './components/OsSwitcher'
import type { EnvironmentProfile, RunResult } from './api/types'
import { Desktop } from './screens/Desktop'
import { ParameterConfiguration } from './screens/ParameterConfiguration'
import { Preparing } from './screens/Preparing'
import { Verdict } from './screens/Verdict'
import { useOsTheme } from './theme/useOsTheme'

type ScreenState =
  | { name: 'desktop' }
  | { name: 'config' }
  | { name: 'preparing'; profile: EnvironmentProfile }
  | { name: 'verdict'; result: RunResult }

export default function App() {
  const { os, setOs } = useOsTheme()
  const [screen, setScreen] = useState<ScreenState>({ name: 'desktop' })
  const [projectOpen, setProjectOpen] = useState(true)

  /* The folder icon is always on screen, so it has to do the whole job:
     come back to the desktop AND reopen the project dialog. Setting the
     screen alone did nothing when the desktop was already showing. */
  function openProject() {
    setScreen({ name: 'desktop' })
    setProjectOpen(true)
  }

  return (
    <>
      <OsSwitcher os={os} onChange={setOs} />

      {/* Desktop furniture: present on every screen, so it is rendered once
          here rather than per screen. Clicking the folder always returns to
          the desktop, where the upload dialog lives. */}
      <DesktopCorners os={os} onFolderClick={openProject} />

      {screen.name === 'desktop' && (
        <Desktop
          os={os}
          open={projectOpen}
          onOpenChange={setProjectOpen}
          onStart={() => setScreen({ name: 'config' })}
        />
      )}

      {screen.name === 'config' && (
        <ParameterConfiguration
          os={os}
          onEnterEnvironment={(profile) => setScreen({ name: 'preparing', profile })}
        />
      )}

      {screen.name === 'preparing' && (
        <Preparing
          os={os}
          profile={screen.profile}
          onDone={(result) => setScreen({ name: 'verdict', result })}
        />
      )}

      {screen.name === 'verdict' && (
        <Verdict os={os} result={screen.result} onBack={() => setScreen({ name: 'config' })} />
      )}
    </>
  )
}
