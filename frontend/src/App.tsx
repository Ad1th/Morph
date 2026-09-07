import { useState } from 'react'
import { OsSwitcher } from './components/OsSwitcher'
import type { EnvironmentProfile, RunResult } from './api/types'
import { Desktop } from './screens/Desktop'
import { Experiment } from './screens/Experiment'
import { ParameterConfiguration } from './screens/ParameterConfiguration'
import { Preparing } from './screens/Preparing'
import { Verdict } from './screens/Verdict'
import { useOsTheme } from './theme/useOsTheme'

type ScreenState =
  | { name: 'desktop' }
  | { name: 'config' }
  | { name: 'preparing'; profile: EnvironmentProfile }
  | { name: 'verdict'; result: RunResult }
  | { name: 'experiment' }

export default function App() {
  const { os, setOs } = useOsTheme()
  const [screen, setScreen] = useState<ScreenState>({ name: 'desktop' })

  return (
    <>
      <OsSwitcher os={os} onChange={setOs} />

      {screen.name === 'desktop' && (
        <Desktop
          os={os}
          onStart={() => setScreen({ name: 'config' })}
          onExperiment={() => setScreen({ name: 'experiment' })}
        />
      )}

      {screen.name === 'experiment' && (
        <Experiment os={os} onBack={() => setScreen({ name: 'desktop' })} />
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
