import { useState, type ReactNode } from 'react'
import './ParamGroup.css'

export function ParamGroup({
  name,
  nonDefaultCount,
  defaultOpen = false,
  children,
}: {
  name: string
  nonDefaultCount: number
  defaultOpen?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="param-group" data-open={open}>
      <button className="param-group__header" onClick={() => setOpen((v) => !v)}>
        <span className="param-group__chevron">{open ? '▾' : '▸'}</span>
        <span className="param-group__name">{name}</span>
        <span className="param-group__count">{nonDefaultCount} non-default</span>
      </button>
      {open && <div className="param-group__body">{children}</div>}
    </div>
  )
}
