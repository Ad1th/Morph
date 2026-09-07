import { useEffect, useRef } from 'react'
import Lenis from 'lenis'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

/* Drives one number: `progress.current` in [0, 1], the scrub position of the
   camera flight. Lenis smooths the wheel/touch input, ScrollTrigger maps the
   spacer's scroll range onto a raw target, and a per-frame critical-damp pass
   makes the camera ease rather than track the pointer 1:1 — nothing in the
   journey is allowed to snap. `onFrame` runs after each damp step for the DOM
   overlay; the 3D layer reads `progress.current` directly in its own loop. */
export function useJourneyScroll(
  spacerRef: React.RefObject<HTMLElement | null>,
  onFrame: (p: number) => void,
) {
  const progress = useRef(0)
  const onFrameRef = useRef(onFrame)
  useEffect(() => {
    onFrameRef.current = onFrame
  }, [onFrame])

  useEffect(() => {
    const spacer = spacerRef.current
    if (!spacer) return

    /* `?static` drops Lenis so automated screenshots can jump with a plain
       window.scrollTo; ScrollTrigger reads native scroll either way. */
    const useLenis = !window.location.search.includes('static')
    const lenis = useLenis ? new Lenis({ lerp: 0.1, wheelMultiplier: 0.7 }) : null
    lenis?.on('scroll', ScrollTrigger.update)

    const tickerFn = (time: number) => lenis?.raf(time * 1000)
    if (lenis) {
      gsap.ticker.add(tickerFn)
      gsap.ticker.lagSmoothing(0)
    }

    let target = 0
    const trigger = ScrollTrigger.create({
      trigger: spacer,
      start: 'top top',
      end: 'bottom bottom',
      scrub: true,
      onUpdate: (self) => {
        target = self.progress
      },
    })

    let raf = 0
    const loop = () => {
      progress.current += (target - progress.current) * 0.06
      onFrameRef.current(progress.current)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(raf)
      trigger.kill()
      gsap.ticker.remove(tickerFn)
      lenis?.destroy()
    }
  }, [spacerRef])

  return progress
}
