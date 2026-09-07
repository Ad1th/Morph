import { ANNOTATIONS } from './scenes'

/* Shown when the visitor asked for reduced motion (or WebGL is unavailable).
   The camera flight collapses to an editorial list: the same four knobs,
   laid out to be read rather than flown through. */
export function JourneyStill() {
  return (
    <section className="journey-still">
      <h1 className="hero-mark">Morph</h1>
      <p className="hero-line">
        Test your software in environments you don&rsquo;t physically have.
      </p>
      <p className="hero-sub">
        Capture what a user&rsquo;s machine is like, recreate it on the one in front
        of you, and run experiments until you know which condition broke the build.
      </p>
      <ol>
        {ANNOTATIONS.map((a) => (
          <li key={a.id}>
            <h3>{a.tag}</h3>
            <code className="annotation-readout">{a.readout}</code>
            <p>{a.body}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}
