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
        <Loop />
        <Honesty />
        <Measurements />
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
            <p className="hero-sub">
              Capture what a user&rsquo;s machine is like, recreate it on the one in
              front of you, and run experiments until you know which condition
              broke the build.
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
              <code className="annotation-readout">{a.readout}</code>
              <p className="annotation-body">{a.body}</p>
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

/* The flight you just took, in the words a developer would use, next to the
   transcript of a real run. Every number here was printed by `morph demo`
   on a MacBook with no root: it is not illustrative. */
function Loop() {
  return (
    <section className="loop" id="how">
      <div className="loop-text">
        <h2 className="section-title">
          A customer&rsquo;s laptop, a flaky network, and a checkout that only fails
          for them.
        </h2>
        <p>
          Morph starts with a profile of that laptop: cores, memory, locale, timezone,
          and what its network looks like. It applies those conditions on your machine,
          then runs your program under each one on its own, and under all of them
          together, in matched pairs against a clean baseline.
        </p>
        <p>
          The evidence it shows while the trials run is an e‑value, not a p‑value.
          You can watch it climb and stop the moment it crosses the line without
          inflating your false‑positive rate. That is what lets a run finish in nine
          pairs instead of a fixed hundred.
        </p>
        <p>
          When it is done you get a verdict, the smallest set of conditions that still
          reproduces the failure, and a regression bundle you can replay after the fix.
        </p>
      </div>
      <figure className="terminal" aria-label="Transcript of morph demo">
        <figcaption>
          <span>morph demo</span>
          <span>MacBook, no root, 1 min 46 s</span>
        </figcaption>
        <pre>
{`sequential isolation  α 0.05  K 3  reject at E ≥ 60

baseline        `}<i className="ok">●●●●●●●●●●●●</i>{`             0/12
latency_only    `}<i className="ok">●●●●●●●●●●●●</i>{`   E 1.0     0/12
loss_only       `}<i className="ok">●●●●●●●●●●●●</i>{`   E 1.0     0/12
full_treatment  `}<i className="bad">○○○○○○○○○</i>{`      `}<b>E 102  decisive</b>{`  9/9
                stopped early after 9 pairs

Δ risk  +100 %  [+61 %, +100 %]     anytime p 0.0098
`}<b className="verdict">environment_caused</b>{`   minimal set  latency, packet loss`}
        </pre>
      </figure>
    </section>
  )
}

/* What the tool will and will not pretend to do. Unusual on a landing page,
   and the most trusted thing on it. */
function Honesty() {
  const rows: [string, string][] = [
    ['Network latency, packet loss, bandwidth', 'A real network path. Shaping models one.'],
    ['CPU quota and core count', 'Clock speed or cache of a chip you do not own.'],
    ['Memory limits', 'Turning 8 GB into 16 GB. It cannot, so it says so.'],
    ['Locale, timezone, file descriptors, process count', 'Every kernel and driver detail.'],
    ['Case sensitivity of the filesystem', 'Making macOS behave like Windows.'],
  ]
  return (
    <section className="honesty">
      <h2 className="section-title">What it reproduces, and what it refuses to claim.</h2>
      <p className="section-lede">
        Every field in a profile is stamped by the code that applied it: reproduced,
        approximated, or unavailable, with the reason. A run that could not launch is
        an invalid trial, not a failure. A boundary search that never sees a failure
        says there is no boundary in range instead of inventing one.
      </p>
      <table className="honesty-table">
        <thead>
          <tr>
            <th scope="col">Reproduces</th>
            <th scope="col">Does not claim</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([yes, no]) => (
            <tr key={yes}>
              <td>{yes}</td>
              <td>{no}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

/* Three measurements from the test suite and the paper trail behind them,
   set as a ledger. They are the reason the live console is allowed to exist. */
function Measurements() {
  return (
    <section className="measure">
      <h2 className="section-title">Measured, not promised.</h2>
      <dl className="ledger">
        <div>
          <dt>2.1 %</dt>
          <dd>
            false positives when the e‑value is watched continuously at α = 5 %, over
            1,500 simulated no-effect runs. Ville&rsquo;s inequality guarantees at most 5.
          </dd>
        </div>
        <div>
          <dt>7 pairs</dt>
          <dd>
            to decide the flagship fault, latency plus packet loss against a clean
            baseline. A fixed batch design needs every one of its trials before it can
            say anything.
          </dd>
        </div>
        <div>
          <dt>4 ms vs 21 ms</dt>
          <dd>
            median error locating a noisy 150 ms failure boundary, probabilistic
            bisection against plain bisection on the same trial budget. Worst cases
            were 24 ms and 150 ms.
          </dd>
        </div>
      </dl>
      <p className="measure-note">
        The statistics are Robbins&rsquo; mixture e-process (Ramdas, Grünwald, Vovk and
        Shafer, 2023), Horstein&rsquo;s probabilistic bisection (Waeber, Frazier and
        Henderson, 2013) and Zeller&rsquo;s delta debugging. Morph invented none of
        them. It points them at a machine.
      </p>
    </section>
  )
}

function Products() {
  return (
    <section className="products" id="get">
      <h2 className="section-title products-title">Two ways to run it.</h2>

      <article className="product product-local">
        <p className="product-kicker">Open source, free</p>
        <h3 className="product-name">Morph Local</h3>
        <p className="product-copy">
          Everything on this page runs on your own machine with no root. Network shaping
          uses a user-space proxy on macOS and Windows; on Linux, or over SSH to a
          Raspberry Pi, cgroups make the CPU and memory limits real.
        </p>
        <pre className="install"><code>{`git clone https://github.com/Ad1th/Morph && cd Morph
pip install -r requirements.txt && pip install -e .
morph demo`}</code></pre>
        <div className="product-cta">
          <a className="btn" href="https://github.com/Ad1th/Morph" target="_blank" rel="noreferrer">
            Star on GitHub
          </a>
          <a
            className="btn"
            href="https://github.com/Ad1th/Morph/blob/main/docs/how-it-works.md"
            target="_blank"
            rel="noreferrer"
          >
            Read how it works
          </a>
        </div>
      </article>

      <article className="product product-fleet">
        <p className="product-kicker">Cloud, for teams</p>
        <h3 className="product-name">Morph Fleet</h3>
        <p className="product-copy">
          The same engine on workers we run, so a profile that needs more cores, more
          memory or another architecture than your laptop has goes to a machine that
          has it. Sweep a whole matrix of environments in parallel and keep the
          regression bundles with the repo.
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
      <span>Morph. Built at Code2Create 7.0, ACM-VIT.</span>
      <nav>
        <a href="https://github.com/Ad1th/Morph" target="_blank" rel="noreferrer">
          github.com/Ad1th/Morph
        </a>
        <a
          href="https://github.com/Ad1th/Morph/blob/main/docs/how-it-works.md"
          target="_blank"
          rel="noreferrer"
        >
          how it works
        </a>
        <a href="https://github.com/Ad1th/Morph/blob/main/docs/tui.md" target="_blank" rel="noreferrer">
          the console
        </a>
      </nav>
    </footer>
  )
}
