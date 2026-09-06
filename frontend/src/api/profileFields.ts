import type { EnvironmentProfile, FieldStatus, ProfileField } from './types'

type AnyRecord = Record<string, unknown>

/** Reads the ProfileField at a dotted field_path (e.g. "network.jitter_ms"). */
export function getField(profile: EnvironmentProfile, path: string): ProfileField | undefined {
  let obj: unknown = profile
  for (const part of path.split('.')) {
    if (obj == null || typeof obj !== 'object') return undefined
    obj = (obj as AnyRecord)[part]
  }
  return obj as ProfileField | undefined
}

/** Returns a new profile with the field at `path` set to `value`. Creates
 * intermediate objects if the path doesn't resolve (e.g. the field was never
 * captured/requested before). */
export function setFieldValue(
  profile: EnvironmentProfile,
  path: string,
  value: unknown,
  status: FieldStatus = 'requested',
): EnvironmentProfile {
  const parts = path.split('.')
  const clone = structuredClone(profile) as unknown as AnyRecord
  let obj = clone
  for (let i = 0; i < parts.length - 1; i++) {
    const key = parts[i]
    if (obj[key] == null || typeof obj[key] !== 'object') obj[key] = {}
    obj = obj[key] as AnyRecord
  }
  obj[parts[parts.length - 1]] = { value, status }
  return clone as unknown as EnvironmentProfile
}
