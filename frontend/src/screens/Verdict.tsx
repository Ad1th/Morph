import { useState } from 'react'
import { api } from '../api/client'
import type { DifferentialBlameResult, ExportInvariantResponse, RunResult } from '../api/types'
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
  const [blame, setBlame] = useState<DifferentialBlameResult | null>(null)
  const [analyzingBlame, setAnalyzingBlame] = useState(false)
  const [exportResult, setExportResult] = useState<ExportInvariantResponse | null>(null)
  const [copied, setCopied] = useState(false)

  async function handleDiagnoseBlame() {
    setAnalyzingBlame(true)
    try {
      const b = await api.analyzeBlame({
        pass_output: 'HTTP 200 (duration: 172ms)',
        fail_output: `${result.stdout}\n${result.stderr}`,
        pass_param_label: 'Baseline Pass',
        fail_param_label: `Failure (${result.duration_ms.toFixed(0)}ms)`,
      })
      setBlame(b)
    } catch (err) {
      console.error(err)
    }
    setAnalyzingBlame(false)
  }

  async function handleExportInvariant() {
    try {
      const exp = await api.exportInvariant({
        project_name: 'service',
        safe_latency_ms: 160.0,
        safe_packet_loss: 0.01,
        boundary_estimate: 180.0,
        divergence_summary: blame?.divergence_summary,
      })
      setExportResult(exp)
    } catch (err) {
      console.error(err)
    }
  }

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

        {/* Feature 2: Differential Runtime Blame on Verdict screen */}
        {!result.passed && (
          <div className="verdict__diagnostics">
            {!blame ? (
              <button
                className="verdict__btn-blame"
                onClick={handleDiagnoseBlame}
                disabled={analyzingBlame}
              >
                {analyzingBlame ? 'Analyzing Stack & Telemetry…' : '🔍 Differential Runtime Blame (Isolate Culprit Code)'}
              </button>
            ) : (
              <div className="verdict__blame-card">
                <div className="verdict__blame-badge">Differential Runtime Blame</div>
                <div className="verdict__blame-culprit">
                  Culprit Line: <code>{blame.culpable_file}:{blame.culpable_line}</code>
                </div>
                {blame.pass_trace && (
                  <div className="verdict__blame-line verdict__blame-line--pass">
                    <span>PASS:</span> <code>{blame.pass_trace.summary_line}</code>
                  </div>
                )}
                {blame.fail_trace && (
                  <div className="verdict__blame-line verdict__blame-line--fail">
                    <span>FAIL:</span> <code>{blame.fail_trace.summary_line}</code>
                  </div>
                )}
                {blame.culpable_code && (
                  <pre className="verdict__blame-code">
                    <code>{blame.culpable_code}</code>
                  </pre>
                )}
                <div className="verdict__blame-exp">
                  <strong>Diagnosis:</strong> {blame.explanation}
                </div>
                {blame.suggested_fix && (
                  <div className="verdict__blame-fix">
                    <strong>Fix:</strong> {blame.suggested_fix}
                  </div>
                )}

                {/* Feature 3: Executable Invariant Exporter */}
                <div style={{ marginTop: '0.75rem' }}>
                  <button
                    className="verdict__btn-export"
                    onClick={handleExportInvariant}
                  >
                    ⚡ Export Invariant Guardrail (test_morph_invariant.py)
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {exportResult && (
          <div className="verdict__export-box">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#3fb950' }}>{exportResult.filename}</span>
              <button
                className="verdict__copy-btn"
                onClick={() => {
                  navigator.clipboard.writeText(exportResult.code)
                  setCopied(true)
                  setTimeout(() => setCopied(false), 2000)
                }}
              >
                {copied ? '✓ Copied' : 'Copy Test Code'}
              </button>
            </div>
            <pre className="verdict__export-code">
              <code>{exportResult.code}</code>
            </pre>
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
