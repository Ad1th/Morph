/* The camera flight is a fixed sequence of scenes. Both the 3D camera path and
   the DOM overlay read from this one table so a timing tweak stays in sync. */

export type Annotation = {
  id: 'cpu' | 'ram' | 'locale' | 'rlimit'
  className: string
  tag: string
  /* The instrument readout: the real knob Morph turns, in its real units. */
  readout: string
  body: string
  from: number
  to: number
}

export const ANNOTATIONS: Annotation[] = [
  {
    id: 'cpu',
    className: 'annotation a-cpu',
    tag: 'cpu',
    readout: 'cpu.max  40000 100000',
    body:
      'The child process gets 40 ms of CPU in every 100 ms window. When the quota is spent the scheduler freezes it until the next window, which is what a busy four-core laptop feels like from inside.',
    from: 0.29,
    to: 0.46,
  },
  {
    id: 'ram',
    className: 'annotation a-ram',
    tag: 'memory',
    readout: 'memory.max  8589934592',
    body:
      'The cgroup memory controller bounds the process at the captured size. Allocate past it and the kernel OOM killer answers, exactly as it would on the machine you are imitating.',
    from: 0.46,
    to: 0.6,
  },
  {
    id: 'locale',
    className: 'annotation a-locale',
    tag: 'locale and timezone',
    readout: 'LANG=en_IN.UTF-8  TZ=Asia/Kolkata',
    body:
      'Both are read from the captured profile and placed in the environment before the process starts, so dates, decimal separators and DST behave the way they do for the user, not for you.',
    from: 0.6,
    to: 0.74,
  },
  {
    id: 'rlimit',
    className: 'annotation a-rlimit',
    tag: 'process limits',
    readout: 'RLIMIT_NOFILE=256  RLIMIT_NPROC=64',
    body:
      'File descriptors and process count are set with POSIX rlimits just before exec. A pool that leaks handles fails here at the same count it failed at in production.',
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
