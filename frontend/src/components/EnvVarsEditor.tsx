import { Icon } from './ui/Icon'

const RESERVED = new Set(['PATH', 'HOME'])

export function EnvVarsEditor({
  vars,
  onChange,
}: {
  vars: Record<string, string>
  onChange: (next: Record<string, string>) => void
}) {
  const entries = Object.entries(vars)

  function update(index: number, key: string, value: string) {
    const next: Record<string, string> = {}
    entries.forEach(([k, v], i) => {
      if (i === index) next[key] = value
      else next[k] = v
    })
    onChange(next)
  }

  function remove(index: number) {
    const next: Record<string, string> = {}
    entries.forEach(([k, v], i) => i !== index && (next[k] = v))
    onChange(next)
  }

  function add() {
    let name = 'NEW_VAR'
    let n = 1
    while (name in vars) name = `NEW_VAR_${n++}`
    onChange({ ...vars, [name]: '' })
  }

  const keys = entries.map(([k]) => k)
  const dupes = new Set(keys.filter((k, i) => keys.indexOf(k) !== i))

  return (
    <div className="envvars">
      <p className="small muted">Overlaid on the host environment. PATH and HOME are reserved.</p>
      {entries.map(([key, value], i) => {
        const warn = RESERVED.has(key) ? 'reserved name' : dupes.has(key) ? 'duplicate key' : null
        return (
          <div className="envvars__row" key={i}>
            <input
              className="input"
              aria-label={`Variable ${i + 1} name`}
              aria-invalid={warn ? true : undefined}
              value={key}
              onChange={(e) => update(i, e.target.value, value)}
            />
            <span className="faint">=</span>
            <input
              className="input"
              aria-label={`Variable ${i + 1} value`}
              value={value}
              onChange={(e) => update(i, key, e.target.value)}
            />
            <button className="btn btn--ghost btn--icon" onClick={() => remove(i)} aria-label={`Remove ${key}`}>
              <Icon name="x" size={14} />
            </button>
            {warn && <span className="field__error envvars__warn">{warn}</span>}
          </div>
        )
      })}
      <button className="btn btn--sm" onClick={add}>
        <Icon name="plus" size={13} />
        Add variable
      </button>
    </div>
  )
}
