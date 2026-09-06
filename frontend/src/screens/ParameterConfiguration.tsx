import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { getField, setFieldValue } from '../api/profileFields'
import type { EnvironmentProfile, ParameterMetadata } from '../api/types'
import { EnvVarsEditor } from '../components/EnvVarsEditor'
import { ParamGroup } from '../components/ParamGroup'
import { ParameterRow } from '../components/ParameterRow'
import type { OsName } from '../theme/useOsTheme'
import { PARAM_GROUPS } from './paramGroups'
import { formatSummary } from './summaryString'
import './ParameterConfiguration.css'

export function ParameterConfiguration({
  os,
  onEnterEnvironment,
}: {
  os: OsName
  onEnterEnvironment: (profile: EnvironmentProfile) => void
}) {
  const [profile, setProfile] = useState<EnvironmentProfile | null>(null)
  const [catalog, setCatalog] = useState<Record<string, ParameterMetadata> | null>(null)
  const [search, setSearch] = useState('')
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.captureProfile(), api.getParameterCatalog()])
      .then(([p, c]) => {
        setProfile(p)
        setCatalog(c)
      })
      .catch((err) => setLoadError(String(err)))
  }, [])

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
          <span>{os === 'linux' ? '$ configure-environment' : 'Parameter Configuration — Morph'}</span>
        </div>

        <div className="param-config__summary">{summary || 'All parameters at host defaults'}</div>

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
            onClick={() => onEnterEnvironment(profile)}
          >
            Enter Environment
          </button>
        </div>
      </div>
    </div>
  )
}
