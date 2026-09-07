/* The camera flight is a fixed sequence of scenes. Both the 3D camera path and
   the DOM overlay read from this one table so a timing tweak stays in sync. */

export type Annotation = {
  id: 'cpu' | 'ram' | 'locale' | 'rlimit'
  className: string
  tag: string
  /* `body` is HTML — a single <b> marks the measured value, nothing else. */
  body: string
  from: number
  to: number
}

export const ANNOTATIONS: Annotation[] = [
  {
    id: 'cpu',
    className: 'annotation a-cpu',
    tag: 'cpu / cores',
    body:
      'Child processes are capped with cgroups and frozen by the kernel scheduler when the quota runs out — <b>40 ms of runtime inside every 100 ms window</b>.',
    from: 0.29,
    to: 0.46,
  },
  {
    id: 'ram',
    className: 'annotation a-ram',
    tag: 'memory',
    body:
      'Memory is bounded by the cgroup memory controller. Overcommit past the limit is settled by the <b>kernel OOM killer</b>, exactly as it would be on the target.',
    from: 0.46,
    to: 0.6,
  },
  {
    id: 'locale',
    className: 'annotation a-locale',
    tag: 'locale / timezone',
    body:
      'Locale and timezone are read from the captured profile and pushed into the sandbox <b>before the process starts</b>, so date and number formatting match.',
    from: 0.6,
    to: 0.74,
  },
  {
    id: 'rlimit',
    className: 'annotation a-rlimit',
    tag: 'process limits',
    body:
      'Threads, file descriptors and process count are constrained before exec with POSIX rlimits — <b>RLIMIT_NOFILE and RLIMIT_NPROC</b>.',
    from: 0.6,
    to: 0.74,
  },
]

export type Scene = { at: number; label: string; title: string }

export const SCENES: Scene[] = [
  { at: 0.0, label: 'scene 00', title: 'the machine you have' },
  { at: 0.12, label: 'scene 01', title: 'past the panel' },
  { at: 0.29, label: 'scene 02', title: 'into the silicon' },
  { at: 0.46, label: 'scene 03', title: 'the memory' },
  { at: 0.6, label: 'scene 04', title: 'across the board' },
  { at: 0.74, label: 'scene 05', title: 'the morph' },
  { at: 0.92, label: 'scene 06', title: 'the machine you don’t' },
]

export const TOTAL_FRAMES = 760

export function sceneAt(p: number): Scene {
  let current = SCENES[0]
  for (const s of SCENES) if (p >= s.at) current = s
  return current
}
