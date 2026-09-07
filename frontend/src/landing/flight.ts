/* Shared, non-reactive flight state. The <Rig> writes it once per frame from
   the scroll progress; every mesh reads it in its own useFrame and eases its
   own material/transform toward the target. Keeping it out of React state is
   deliberate — 60fps mutation of a dozen meshes should not re-render a tree. */
export const flight = {
  /** raw scrub progress, 0..1 */
  p: 0,
  /** 0 before the morph, 1 after — smootherstepped over the morph window */
  morph: 0,
  /** emissive drive for the PCB traces */
  glow: 0.6,
}

export function smoothstep(a: number, b: number, x: number) {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

export function smootherstep(a: number, b: number, x: number) {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * t * (t * (t * 6 - 15) + 10)
}

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t
