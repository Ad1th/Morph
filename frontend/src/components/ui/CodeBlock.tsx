import { useEffect, useState } from 'react'
import { Icon } from './Icon'

/** Monospace block with a copy button. The one shared implementation for
 *  logs, exported tests and JSON. */
export function CodeBlock({
  code,
  filename,
  maxHeight = 320,
  wrap = false,
}: {
  code: string
  filename?: string
  maxHeight?: number
  wrap?: boolean
}) {
  const [copied, setCopied] = useState<'idle' | 'ok' | 'fail'>('idle')

  useEffect(() => {
    if (copied === 'idle') return
    const t = window.setTimeout(() => setCopied('idle'), 1800)
    return () => window.clearTimeout(t)
  }, [copied])

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied('ok')
    } catch {
      setCopied('fail')
    }
  }

  return (
    <div className="codeblock">
      <div className="codeblock__bar">
        <span className="small muted">{filename ?? ''}</span>
        <button className="btn btn--ghost btn--sm" onClick={copy} aria-live="polite">
          <Icon name={copied === 'ok' ? 'check' : 'copy'} size={14} />
          {copied === 'ok' ? 'Copied' : copied === 'fail' ? 'Copy blocked' : 'Copy'}
        </button>
      </div>
      <pre className="code" style={{ maxHeight, whiteSpace: wrap ? 'pre-wrap' : 'pre' }}>
        <code>{code || '(empty)'}</code>
      </pre>
    </div>
  )
}
