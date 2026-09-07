import { Component, type ReactNode, useRef, useState } from 'react'
import './landing.css'
import { ANNOTATIONS, SCENES, TOTAL_FRAMES, sceneAt } from './scenes'
import { useJourneyScroll } from './useJourneyScroll'
import { JourneyStill } from './JourneyStill'
import { Journey3D } from './Journey3D'

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function Landing() {
  const [reduced] = useState(prefersReducedMotion)

  return (
    <div className="landing">
      {reduced ? (
        <JourneyStill />
      ) : (
        <WebglBoundary fallback={<JourneyStill />}>
          <Journey />
        </WebglBoundary>
      )}
      <div className="after">
        <Products />
        <Footer />
      </div>
    </div>
  )
}

function Journey() {
  const rootRef = useRef<HTMLDivElement>(null)
  const spacerRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<HTMLSpanElement>(null)
  const labelRef = useRef<HTMLSpanElement>(null)
  const titleRef = useRef<HTMLSpanElement>(null)
  const annRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const lastScene = useRef('')

  const onFrame = (p: number) => {
    const root = rootRef.current
    if (root) root.style.setProperty('--p', p.toFixed(4))

    if (frameRef.current) {
      const f = Math.round(p * TOTAL_FRAMES)
      frameRef.current.textContent = `${String(f).padStart(4, '0')} / ${TOTAL_FRAMES}`
    }
    const scene = sceneAt(p)
    if (scene.label !== lastScene.current) {
      lastScene.current = scene.label
      if (labelRef.current) labelRef.current.textContent = scene.label
      if (titleRef.current) titleRef.current.textContent = scene.title
    }
    for (const a of ANNOTATIONS) {
      const el = annRefs.current[a.id]
      if (el) el.dataset.on = String(p >= a.from && p < a.to)
    }
  }

  const progress = useJourneyScroll(spacerRef, onFrame)

  return (
    <>
      <div className="journey-stage" ref={rootRef}>
        <Journey3D progress={progress} />
        <div className="journey-overlay">
          <div className="hero">
            <h1 className="hero-mark">Morph</h1>
            <p className="hero-line">
              Test your software in environments you don&rsquo;t physically have.
            </p>
          </div>
          <div />
          <div className="hud">
            <span className="hud-frame" ref={frameRef}>
              0000 / {TOTAL_FRAMES}
            </span>
            <span className="hud-scene">
              <span ref={labelRef}>{SCENES[0].label}</span>
            </span>
            <span className="hud-title" ref={titleRef}>
              {SCENES[0].title}
            </span>
          </div>
          <span className="scroll-cue">scroll to fly through</span>
        </div>
        <div className="annotations">
          {ANNOTATIONS.map((a) => (
            <div
              key={a.id}
              className={a.className}
              data-on="false"
              ref={(el) => {
                annRefs.current[a.id] = el
              }}
            >
              <span className="annotation-leader" />
              <span className="annotation-tag">{a.tag}</span>
              <p
                className="annotation-body"
                dangerouslySetInnerHTML={{ __html: a.body }}
              />
            </div>
          ))}
        </div>
      </div>
      <div className="journey-spacer" ref={spacerRef} />
    </>
  )
}

class WebglBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

function Products() {
  return (
    <section className="products">
      <p className="products-lede">One capture. Every machine you can&rsquo;t hold.</p>

      <article className="product product-local">
        <span className="product-kicker">open source / free</span>
        <h2 className="product-name">Morph Local</h2>
        <p className="product-copy">
          Run it on your own Linux box — or SSH into a Raspberry Pi for the most
          faithful CPU-level reproduction. Every other condition can be replicated
          without a Linux environment.
        </p>
        <div className="product-cta">
          <a
            className="btn"
            href="https://github.com/Ad1th/Morph"
            target="_blank"
            rel="noreferrer"
          >
            Star on GitHub
          </a>
          <a className="btn" href="https://github.com/Ad1th/Morph#readme" target="_blank" rel="noreferrer">
            Read the docs
          </a>
        </div>
      </article>

      <article className="product product-fleet">
        <span className="product-kicker">cloud / teams</span>
        <h2 className="product-name">Morph Fleet</h2>
        <p className="product-copy">
          Point your app at our cloud workers and sweep hundreds of environment
          combinations in parallel — the whole matrix, not one machine at a time.
        </p>
        <div className="product-cta">
          <a className="btn btn-primary" href="mailto:hello@morph.dev?subject=Morph%20Fleet%20access">
            Request access
          </a>
        </div>
      </article>
    </section>
  )
}

function Footer() {
  return (
    <footer className="landing-footer">
      <span>Morph — made at Code2Create 7.0, ACM-VIT</span>
      <a href="https://github.com/Ad1th/Morph" target="_blank" rel="noreferrer">
        github.com/Ad1th/Morph
      </a>
    </footer>
  )
}
