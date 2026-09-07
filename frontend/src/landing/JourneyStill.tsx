import { ANNOTATIONS } from './scenes'

/* Shown when the visitor asked for reduced motion (or WebGL is unavailable).
   The camera flight collapses to an editorial list — same four measurements,
   laid out to be read rather than flown through. */
export function JourneyStill() {
  return (
    <section className="journey-still">
      <h1 className="hero-mark">Morph</h1>
      <p className="hero-line">
        Test your software in environments you don&rsquo;t physically have. Morph
        captures a machine&rsquo;s conditions and reproduces them where your code
        actually runs.
      </p>
      <ol>
        {ANNOTATIONS.map((a) => (
          <li key={a.id}>
            <h3>{a.tag}</h3>
            <p dangerouslySetInnerHTML={{ __html: a.body }} />
          </li>
        ))}
      </ol>
    </section>
  )
}
