import { useState } from 'react'
import type { RunResult } from '../api/types'
import type { OsName } from '../theme/useOsTheme'
import './Verdict.css'

export function Verdict({
  os,
  result,
  onBack,
}: {
  os: OsName
  result: RunResult
  onBack: () => void
}) {
  const [showOutput, setShowOutput] = useState(false)

  return (
    <div className="verdict" data-os={os}>
      <div className="verdict__panel">
        <div className="verdict__banner" data-passed={result.passed}>
          {result.passed ? 'PASS' : 'FAIL'}
        </div>

        <div className="verdict__metrics">
          <Metric label="Exit code" value={String(result.exit_code)} />
          <Metric label="Duration" value={`${result.duration_ms.toFixed(1)} ms`} />
          <Metric
            label="Peak memory"
            value={result.peak_memory_mb != null ? `${result.peak_memory_mb.toFixed(1)} MB` : 'N/A'}
          />
          <Metric label="Run ID" value={result.run_id} />
        </div>

        {!result.passed && (
          <div className="verdict__error">
            <strong>{result.error_type ?? 'Error'}</strong>: {result.error_message ?? 'unknown error'}
          </div>
        )}

        <button className="verdict__toggle" onClick={() => setShowOutput((v) => !v)}>
          {showOutput ? 'Hide' : 'Show'} stdout / stderr
        </button>
        {showOutput && (
          <pre className="verdict__output">
            {result.stdout && `STDOUT:\n${result.stdout}\n`}
            {result.stderr && `STDERR:\n${result.stderr}`}
            {!result.stdout && !result.stderr && '(no output)'}
          </pre>
        )}

        <button className="verdict__back" onClick={onBack}>
          ← Back to Parameter Configuration
        </button>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="verdict__metric">
      <span className="verdict__metric-label">{label}</span>
      <span className="verdict__metric-value">{value}</span>
    </div>
  )
}
