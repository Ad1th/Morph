import './EnvVarsEditor.css'

const RESERVED = new Set(['PATH', 'HOME'])

export function EnvVarsEditor({
  vars,
  onChange,
}: {
  vars: Record<string, string>
  onChange: (next: Record<string, string>) => void
}) {
  const entries = Object.entries(vars)

  function updateEntry(index: number, key: string, value: string) {
    const next: Record<string, string> = {}
    entries.forEach(([k, v], i) => {
      if (i === index) next[key] = value
      else next[k] = v
    })
    onChange(next)
  }

  function removeEntry(index: number) {
    const next: Record<string, string> = {}
    entries.forEach(([k, v], i) => {
      if (i !== index) next[k] = v
    })
    onChange(next)
  }

  function addEntry() {
    let name = 'NEW_VAR'
    let n = 1
    while (name in vars) name = `NEW_VAR_${n++}`
    onChange({ ...vars, [name]: '' })
  }

  const keys = entries.map(([k]) => k)
  const duplicates = new Set(keys.filter((k, i) => keys.indexOf(k) !== i))

  return (
    <div className="env-vars">
      <p className="env-vars__hint">
        Overlaid on host environment · reserved names (PATH, HOME) will warn
      </p>
      {entries.map(([key, value], i) => (
        <div className="env-vars__row" key={i}>
          <input
            className="env-vars__key"
            value={key}
            onChange={(e) => updateEntry(i, e.target.value, value)}
            data-warn={RESERVED.has(key) || duplicates.has(key)}
          />
          <span className="env-vars__eq">=</span>
          <input
            className="env-vars__value"
            value={value}
            onChange={(e) => updateEntry(i, key, e.target.value)}
          />
          <button className="env-vars__remove" onClick={() => removeEntry(i)} aria-label="Remove variable">
            ×
          </button>
        </div>
      ))}
      <button className="env-vars__add" onClick={addEntry}>
        + Add variable
      </button>
    </div>
  )
}
