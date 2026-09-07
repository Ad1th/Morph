import { useId, useState, type ReactNode } from 'react'
import { Icon } from './ui/Icon'

export function ParamGroup({
  name,
  changed,
  defaultOpen = false,
  children,
}: {
  name: string
  changed: number
  defaultOpen?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  const id = useId()
  return (
    <section className="pgroup" data-open={open}>
      <h3>
        <button
          className="pgroup__head"
          aria-expanded={open}
          aria-controls={`${id}-panel`}
          onClick={() => setOpen((v) => !v)}
        >
          <Icon name={open ? 'chevronDown' : 'chevronRight'} size={14} />
          <span>{name}</span>
          <span className="pgroup__count muted small">{changed > 0 ? `${changed} changed` : ''}</span>
        </button>
      </h3>
      <div id={`${id}-panel`} className="pgroup__panel" hidden={!open}>
        {children}
      </div>
    </section>
  )
}
