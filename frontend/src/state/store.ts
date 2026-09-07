// A tiny external store: one object, subscribe/notify, a persisted slice in
// localStorage. Screens read it with `useStore(selector)` and write with
// `update(patch)`, so a parameter edited on Run survives a trip to Threshold.
import { useSyncExternalStore } from 'react'
import type {
  EnvironmentProfile,
  ExperimentMode,
  ExperimentResult,
  ProjectInfo,
  RunResult,
  ThresholdResult,
} from '../api/types'

export type Theme = 'dark' | 'light'

export interface RunDraft {
  project: ProjectInfo | null
  command: string
  cwd: string | null
  target: string
  hostProfile: EnvironmentProfile | null
  profile: EnvironmentProfile | null
  presetName: string | null
  mode: ExperimentMode
  maxRounds: number
  trials: number
  alpha: number
  timeoutSec: number
}

export interface AppState {
  theme: Theme
  draft: RunDraft
  lastRun: RunResult | null
  lastExperimentId: string | null
  lastExperiment: ExperimentResult | null
  lastThresholdId: string | null
  lastThreshold: ThresholdResult | null
  lastThresholdParam: string | null
}

const KEY = 'morph.app.v2'

const initialDraft: RunDraft = {
  project: null,
  command: '',
  cwd: null,
  target: 'local',
  hostProfile: null,
  profile: null,
  presetName: null,
  mode: 'sequential',
  maxRounds: 12,
  trials: 5,
  alpha: 0.05,
  timeoutSec: 30,
}

// Dark-first: the product ships dark; the toggle persists a light choice.
function systemTheme(): Theme {
  return 'dark'
}

function load(): AppState {
  const base: AppState = {
    theme: systemTheme(),
    draft: initialDraft,
    lastRun: null,
    lastExperimentId: null,
    lastExperiment: null,
    lastThresholdId: null,
    lastThreshold: null,
    lastThresholdParam: null,
  }
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return base
    const saved = JSON.parse(raw) as Partial<AppState>
    return {
      ...base,
      ...saved,
      draft: { ...initialDraft, ...(saved.draft ?? {}) },
    }
  } catch {
    return base
  }
}

/** Trial output is large and reproducible from the server; keep the numbers. */
function slimExperiment(r: ExperimentResult | null): ExperimentResult | null {
  if (!r) return null
  const slimBatch = (b: ExperimentResult['baseline']) => (b ? { ...b, run_results: [] } : b)
  return {
    ...r,
    baseline: slimBatch(r.baseline),
    comparisons: r.comparisons.map((c) => ({ ...c, baseline: null, treatment: null })),
    interactions: (r.interactions ?? []).map((c) => ({ ...c, baseline: null, treatment: null })),
  }
}

function persist(state: AppState) {
  try {
    const out: AppState = {
      ...state,
      lastExperiment: slimExperiment(state.lastExperiment),
      lastRun: state.lastRun
        ? { ...state.lastRun, stdout: state.lastRun.stdout.slice(-4000), stderr: state.lastRun.stderr.slice(-4000) }
        : null,
    }
    localStorage.setItem(KEY, JSON.stringify(out))
  } catch {
    /* quota or private mode: state stays in memory */
  }
}

let state: AppState = load()
const listeners = new Set<() => void>()

export function getState(): AppState {
  return state
}

export function setState(patch: Partial<AppState> | ((s: AppState) => Partial<AppState>)) {
  const next = typeof patch === 'function' ? patch(state) : patch
  state = { ...state, ...next }
  persist(state)
  listeners.forEach((l) => l())
}

export function updateDraft(patch: Partial<RunDraft> | ((d: RunDraft) => Partial<RunDraft>)) {
  setState((s) => ({ draft: { ...s.draft, ...(typeof patch === 'function' ? patch(s.draft) : patch) } }))
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useStore<T>(selector: (s: AppState) => T): T {
  return useSyncExternalStore(subscribe, () => selector(state), () => selector(state))
}
