import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { getField, setFieldValue } from '../api/profileFields'
import type {
  EnvironmentProfile,
  ParameterMetadata,
  PlatformInfo,
  ProjectInfo,
} from '../api/types'
import { EnvVarsEditor } from '../components/EnvVarsEditor'
import { ParamGroup } from '../components/ParamGroup'
import { ParameterRow } from '../components/ParameterRow'
import { SurfaceHeatmapPanel } from '../components/SurfaceHeatmapPanel'
import { ThresholdPanel } from '../components/ThresholdPanel'
import type { OsName } from '../theme/useOsTheme'
import { PARAM_GROUPS } from './paramGroups'
import { formatSummary } from './summaryString'
import './ParameterConfiguration.css'

export function ParameterConfiguration({
  os,
  project,
  onEnterEnvironment,
}: {
  os: OsName
  /** Null when the user skipped the upload dialog, in which case they type the
      command themselves rather than starting from a detected one. */
  project: ProjectInfo | null
  onEnterEnvironment: (
    profile: EnvironmentProfile,
    command: string,
    cwd: string | undefined,
    target: string,
  ) => void
}) {
  const [profile, setProfile] = useState<EnvironmentProfile | null>(null)
  const [catalog, setCatalog] = useState<Record<string, ParameterMetadata> | null>(null)
  const [search, setSearch] = useState('')
  const [loadError, setLoadError] = useState<string | null>(null)

  // Auto-detection is a guess, so the suggestion is only the starting value.
  const [command, setCommand] = useState(project?.suggested_command ?? '')
  const [platform, setPlatform] = useState<PlatformInfo | null>(null)
  const [platformError, setPlatformError] = useState<string | null>(null)
  const [target, setTarget] = useState('local')

  useEffect(() => {
    Promise.all([api.captureProfile(), api.getParameterCatalog()])
      .then(([p, c]) => {
        setProfile(p)
        setCatalog(c)
      })
      .catch((err) => setLoadError(String(err)))

    // Separate from the pair above: a missing /platform should degrade to the
    // "local" default, not blank out the whole configuration screen.
    api
      .getPlatform()
      .then((info) => {
        setPlatform(info)
        const first = info.targets.find((t) => t.available)
        if (first) setTarget(first.id)
      })
      .catch((err) => setPlatformError(err instanceof Error ? err.message : String(err)))
  }, [])

  const [activeTab, setActiveTab] = useState<'params' | 'threshold' | 'surface'>('params')

  const filter = search.trim().toLowerCase()

  function updateField(fieldPath: string, value: unknown) {
    setProfile((prev) => (prev ? setFieldValue(prev, fieldPath, value) : prev))
  }

  function resetField(fieldPath: string, defaultValue: unknown) {
    setProfile((prev) => (prev ? setFieldValue(prev, fieldPath, defaultValue, 'captured') : prev))
  }

  const summary = useMemo(() => (profile ? formatSummary(profile) : ''), [profile])

  if (loadError) {
    return <div className="param-config__status">Could not reach the Morph backend: {loadError}</div>
  }
  if (!profile || !catalog) {
    return <div className="param-config__status">Capturing host environment…</div>
  }

  return (
    <div className="param-config" data-os={os}>
      <div className="param-config__panel">
        <div className="param-config__titlebar">
          {os === 'mac' && (
            <span className="param-config__traffic-lights">
              <i />
              <i />
              <i />
            </span>
          )}
          <span>{os === 'linux' ? '$ configure-environment' : 'Parameter Configuration - Morph'}</span>
        </div>

        <div className="param-config__summary">{summary || 'All parameters at host defaults'}</div>

        <div className="param-config__tabs">
          <button
            className={`param-config__tab ${activeTab === 'params' ? 'param-config__tab--active' : ''}`}
            onClick={() => setActiveTab('params')}
          >
            ⚙️ Environment Parameters
          </button>
          <button
            className={`param-config__tab ${activeTab === 'threshold' ? 'param-config__tab--active' : ''}`}
            onClick={() => setActiveTab('threshold')}
          >
            📈 1D Threshold Search
          </button>
          <button
            className={`param-config__tab ${activeTab === 'surface' ? 'param-config__tab--active' : ''}`}
            onClick={() => setActiveTab('surface')}
          >
            🗺️ 2D Failure Surface & Blame
          </button>
        </div>

        {activeTab === 'params' && (
          <>
            <input
              className="param-config__search"
              placeholder="Search parameters…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />

            <div className="param-config__groups">
              {PARAM_GROUPS.map((group) => {
                const visibleKeys = group.keys.filter((key) => {
                  const meta = catalog[key]
                  if (!meta) return false
                  if (!filter) return true
                  return meta.name.toLowerCase().includes(filter) || key.includes(filter)
                })
                if (filter && visibleKeys.length === 0) return null

                const nonDefault = group.keys.filter((key) => {
                  const meta = catalog[key]
                  const field = meta && getField(profile, meta.field_path)
                  return field && field.status === 'requested'
                }).length

                return (
                  <ParamGroup
                    key={group.name}
                    name={group.name}
                    nonDefaultCount={nonDefault}
                    defaultOpen={group.name === 'Network' || Boolean(filter)}
                  >
                    {visibleKeys.map((key) => {
                      const meta = catalog[key]
                      const field = getField(profile, meta.field_path)
                      return (
                        <ParameterRow
                          key={key}
                          paramKey={key}
                          meta={meta}
                          field={field}
                          os={os}
                          onChange={(value) => updateField(meta.field_path, value)}
                          onReset={() => resetField(meta.field_path, meta.default ?? null)}
                        />
                      )
                    })}
                  </ParamGroup>
                )
              })}

              {(!filter || 'environment variables'.includes(filter)) && (
                <ParamGroup
                  name="Environment Variables"
                  nonDefaultCount={Object.keys(profile.env_vars).length}
                >
                  <EnvVarsEditor
                    vars={profile.env_vars}
                    onChange={(next) => setProfile((prev) => (prev ? { ...prev, env_vars: next } : prev))}
                  />
                </ParamGroup>
              )}
            </div>
          </>
        )}

        {activeTab === 'threshold' && (
          <div className="param-config__groups">
            <ThresholdPanel
              catalog={catalog}
              profile={profile}
              command={command}
              cwd={project?.suggested_cwd ?? undefined}
              target={target}
            />
          </div>
        )}

        {activeTab === 'surface' && (
          <div className="param-config__groups">
            <SurfaceHeatmapPanel
              catalog={catalog}
              profile={profile}
              command={command}
              cwd={project?.suggested_cwd ?? undefined}
              projectPath={project?.path}
              projectName={project?.name}
            />
          </div>
        )}

        <div className="param-config__run">
          <label className="param-config__run-field">
            <span>Command to run</span>
            <input
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder={project ? 'No entrypoint detected, type a command' : 'py -3 -m apps.timeout test'}
              spellCheck={false}
            />
          </label>

          <label className="param-config__run-field param-config__run-field--narrow">
            <span>Run on</span>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              {platform ? (
                platform.targets.map((t) => (
                  <option
                    key={t.id}
                    value={t.id}
                    disabled={!t.available}
                    title={t.reason ?? undefined}
                  >
                    {t.label}
                    {t.available ? '' : ` (${t.reason ?? 'unavailable'})`}
                  </option>
                ))
              ) : (
                <option value="local">This machine</option>
              )}
            </select>
          </label>

          <p className="param-config__run-note">
            {platformError
              ? `Could not read run targets: ${platformError}`
              : project
                ? `${project.name}: ${project.file_count} file${project.file_count === 1 ? '' : 's'} at ${project.path}`
                : 'No project selected. Type the command to run above.'}
          </p>
        </div>

        <div className="param-config__footer">
          <button
            className="param-config__btn"
            onClick={() => api.captureProfile().then(setProfile)}
          >
            Reset to Host
          </button>
          <button className="param-config__btn" disabled title="Coming soon">
            Load from Captured Profile…
          </button>
          <button className="param-config__btn" disabled title="Coming soon">
            Save as Profile…
          </button>
          <button
            className="param-config__btn param-config__btn--primary"
            onClick={() =>
              onEnterEnvironment(profile, command.trim(), project?.suggested_cwd ?? undefined, target)
            }
            disabled={command.trim() === ''}
            title={command.trim() === '' ? 'Enter a command to run first' : undefined}
          >
            Enter Environment
          </button>
        </div>
      </div>
    </div>
  )
}
