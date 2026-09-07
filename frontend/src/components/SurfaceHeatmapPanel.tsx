import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type {
  EnvironmentProfile,
  ExportInvariantResponse,
  ParameterMetadata,
  SurfaceGridPoint,
  SurfaceResult,
} from '../api/types'
import './SurfaceHeatmapPanel.css'

export function SurfaceHeatmapPanel({
  catalog,
  profile,
  command,
  cwd,
  projectPath,
  projectName,
}: {
  catalog: Record<string, ParameterMetadata>
  profile: EnvironmentProfile
  command: string
  cwd?: string
  projectPath?: string
  projectName?: string
}) {
  const numeric = useMemo(
    () => Object.values(catalog).filter((m) => m.experimentable && m.min != null),
    [catalog],
  )

  const [paramX, setParamX] = useState('network.latency_ms')
  const [paramY, setParamY] = useState('network.packet_loss_percent')
  const [xMin, setXMin] = useState('50')
  const [xMax, setXMax] = useState('300')
  const [xSteps, setXSteps] = useState('6')
  const [yMin, setYMin] = useState('0')
  const [yMax, setYMax] = useState('5')
  const [ySteps, setYSteps] = useState('6')

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [surfaceResult, setSurfaceResult] = useState<SurfaceResult | null>(null)
  const [selectedPoint, setSelectedPoint] = useState<SurfaceGridPoint | null>(null)

  // Invariant export state
  const [exporting, setExporting] = useState(false)
  const [exportResult, setExportResult] = useState<ExportInvariantResponse | null>(null)
  const [copied, setCopied] = useState(false)

  const metaX = numeric.find((m) => m.field_path === paramX)
  const metaY = numeric.find((m) => m.field_path === paramY)

  const canRun =
    !busy &&
    command.trim() !== '' &&
    paramX !== '' &&
    paramY !== '' &&
    Number(xMin) < Number(xMax) &&
    Number(yMin) < Number(yMax)

  async function runSurfaceMapping() {
    setBusy(true)
    setError(null)
    setSelectedPoint(null)
    setExportResult(null)
    try {
      const res = await api.computeSurface({
        project_path: projectPath || 'apps/timeout',
        command: command.trim(),
        cwd,
        param_x: paramX,
        param_y: paramY,
        x_min: Number(xMin),
        x_max: Number(xMax),
        x_steps: Math.max(2, Math.min(10, Number(xSteps) || 6)),
        y_min: Number(yMin),
        y_max: Number(yMax),
        y_steps: Math.max(2, Math.min(10, Number(ySteps) || 6)),
        runs_per_point: 1,
        supplied_profile: profile,
      })
      setSurfaceResult(res)
      if (res.points.length > 0) {
        setSelectedPoint(res.points[0])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
    setBusy(false)
  }

  async function handleExportInvariant() {
    if (!surfaceResult) return
    setExporting(true)
    try {
      const highestPass = surfaceResult.highest_passing_point
      const safeLat = highestPass ? highestPass.x : 160.0
      const safeLoss = highestPass ? highestPass.y : 0.01

      const exp = await api.exportInvariant({
        project_name: projectName || 'target_service',
        command: command.trim(),
        safe_latency_ms: safeLat,
        safe_packet_loss: safeLoss,
        param_name: surfaceResult.param_x,
        boundary_estimate: surfaceResult.lowest_failing_point?.x ?? null,
        divergence_summary: surfaceResult.blame?.divergence_summary,
      })
      setExportResult(exp)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
    setExporting(false)
  }

  function handleCopyCode() {
    if (!exportResult) return
    navigator.clipboard.writeText(exportResult.code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function handleDownloadFile() {
    if (!exportResult) return
    const blob = new Blob([exportResult.code], { type: 'text/x-python' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = exportResult.filename || 'test_morph_invariant.py'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="surface-heatmap">
      <div className="surface-heatmap__header">
        <div>
          <h3 className="surface-heatmap__title">2D Failure Surface & Reliability Envelope</h3>
          <p className="surface-heatmap__subtitle">
            Map out 2-dimensional parameter space to explore failure boundaries, isolate divergent code lines,
            and export automated CI invariant guardrails.
          </p>
        </div>
      </div>

      <div className="surface-heatmap__controls">
        <div className="surface-heatmap__axis-control">
          <div className="surface-heatmap__axis-tag">X-Axis Dimension</div>
          <label className="surface-heatmap__field">
            <span>Parameter</span>
            <select value={paramX} onChange={(e) => setParamX(e.target.value)}>
              {numeric.map((m) => (
                <option key={m.field_path} value={m.field_path}>
                  {m.name} ({m.field_path})
                </option>
              ))}
            </select>
          </label>
          <div className="surface-heatmap__range-row">
            <label className="surface-heatmap__mini-field">
              <span>Min ({metaX?.unit || ''})</span>
              <input type="number" value={xMin} onChange={(e) => setXMin(e.target.value)} />
            </label>
            <label className="surface-heatmap__mini-field">
              <span>Max ({metaX?.unit || ''})</span>
              <input type="number" value={xMax} onChange={(e) => setXMax(e.target.value)} />
            </label>
            <label className="surface-heatmap__mini-field">
              <span>Steps</span>
              <input type="number" min={2} max={10} value={xSteps} onChange={(e) => setXSteps(e.target.value)} />
            </label>
          </div>
        </div>

        <div className="surface-heatmap__axis-control">
          <div className="surface-heatmap__axis-tag">Y-Axis Dimension</div>
          <label className="surface-heatmap__field">
            <span>Parameter</span>
            <select value={paramY} onChange={(e) => setParamY(e.target.value)}>
              {numeric.map((m) => (
                <option key={m.field_path} value={m.field_path}>
                  {m.name} ({m.field_path})
                </option>
              ))}
            </select>
          </label>
          <div className="surface-heatmap__range-row">
            <label className="surface-heatmap__mini-field">
              <span>Min ({metaY?.unit || ''})</span>
              <input type="number" value={yMin} onChange={(e) => setYMin(e.target.value)} />
            </label>
            <label className="surface-heatmap__mini-field">
              <span>Max ({metaY?.unit || ''})</span>
              <input type="number" value={yMax} onChange={(e) => setYMax(e.target.value)} />
            </label>
            <label className="surface-heatmap__mini-field">
              <span>Steps</span>
              <input type="number" min={2} max={10} value={ySteps} onChange={(e) => setYSteps(e.target.value)} />
            </label>
          </div>
        </div>
      </div>

      <div className="surface-heatmap__actions">
        <button
          className="surface-heatmap__btn-primary"
          onClick={runSurfaceMapping}
          disabled={!canRun}
        >
          {busy ? 'Scanning 2D Failure Surface…' : 'Map 2D Failure Surface Heatmap'}
        </button>
      </div>

      {error && <div className="surface-heatmap__error">{error}</div>}

      {surfaceResult && (
        <div className="surface-heatmap__body">
          <div className="surface-heatmap__stat-bar">
            <div className="surface-heatmap__stat-pill">
              <span>Safe Points:</span>
              <strong className="text-emerald">{surfaceResult.passing_count}</strong>
            </div>
            <div className="surface-heatmap__stat-pill">
              <span>Failure Points:</span>
              <strong className="text-coral">{surfaceResult.failing_count}</strong>
            </div>
            <div className="surface-heatmap__stat-pill">
              <span>Total Probes:</span>
              <strong>{surfaceResult.total_points}</strong>
            </div>
            <button
              className="surface-heatmap__export-btn"
              onClick={handleExportInvariant}
              disabled={exporting}
            >
              {exporting ? 'Generating Invariant…' : '⚡ Export Invariant Guardrail (CI/CD)'}
            </button>
          </div>

          <div className="surface-heatmap__layout">
            <div className="surface-heatmap__matrix-container">
              <div className="surface-heatmap__y-title">
                {surfaceResult.param_y_label} ({surfaceResult.param_y_unit}) ↑
              </div>
              <div className="surface-heatmap__matrix-wrapper">
                <div className="surface-heatmap__grid">
                  {surfaceResult.grid.map((row, rowIdx) => {
                    const yVal = surfaceResult.y_values[surfaceResult.y_values.length - 1 - rowIdx]
                    return (
                      <div key={rowIdx} className="surface-heatmap__grid-row">
                        <div className="surface-heatmap__row-label">
                          {yVal}{surfaceResult.param_y_unit}
                        </div>
                        <div className="surface-heatmap__row-cells">
                          {row.map((cell, colIdx) => {
                            const isSelected = selectedPoint?.x === cell.x && selectedPoint?.y === cell.y
                            return (
                              <button
                                key={colIdx}
                                type="button"
                                className={`surface-heatmap__cell ${
                                  cell.passed ? 'surface-heatmap__cell--pass' : 'surface-heatmap__cell--fail'
                                } ${isSelected ? 'surface-heatmap__cell--selected' : ''}`}
                                onClick={() => setSelectedPoint(cell)}
                                title={`${surfaceResult.param_x_label}: ${cell.x}${surfaceResult.param_x_unit}, ${surfaceResult.param_y_label}: ${cell.y}${surfaceResult.param_y_unit} → ${cell.passed ? 'PASS' : 'FAIL'}`}
                              >
                                {cell.passed ? '✓' : '✕'}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })}
                  <div className="surface-heatmap__x-axis">
                    <div className="surface-heatmap__axis-corner" />
                    <div className="surface-heatmap__x-labels">
                      {surfaceResult.x_values.map((xVal, i) => (
                        <div key={i} className="surface-heatmap__x-label">
                          {xVal}{surfaceResult.param_x_unit}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="surface-heatmap__x-title">
                    → {surfaceResult.param_x_label} ({surfaceResult.param_x_unit})
                  </div>
                </div>
              </div>

              <div className="surface-heatmap__legend">
                <div className="surface-heatmap__legend-item">
                  <span className="legend-box legend-box--pass">✓</span>
                  <span>Safe Operational Zone (PASS)</span>
                </div>
                <div className="surface-heatmap__legend-item">
                  <span className="legend-box legend-box--fail">✕</span>
                  <span>Failure Zone (FAIL)</span>
                </div>
              </div>
            </div>

            {selectedPoint && (
              <div className="surface-heatmap__inspector">
                <div className="surface-heatmap__inspector-title">
                  Coordinate Probe Inspection
                </div>
                <div className="surface-heatmap__inspector-row">
                  <span>{surfaceResult.param_x_label}:</span>
                  <strong>{selectedPoint.x} {surfaceResult.param_x_unit}</strong>
                </div>
                <div className="surface-heatmap__inspector-row">
                  <span>{surfaceResult.param_y_label}:</span>
                  <strong>{selectedPoint.y} {surfaceResult.param_y_unit}</strong>
                </div>
                <div className="surface-heatmap__inspector-row">
                  <span>Status:</span>
                  <span className={selectedPoint.passed ? 'text-emerald font-semibold' : 'text-coral font-semibold'}>
                    {selectedPoint.passed ? 'PASS (Exit code 0)' : `FAIL (Exit code ${selectedPoint.exit_code})`}
                  </span>
                </div>
                {selectedPoint.duration_ms != null && (
                  <div className="surface-heatmap__inspector-row">
                    <span>Duration:</span>
                    <strong>{selectedPoint.duration_ms.toFixed(1)} ms</strong>
                  </div>
                )}
                <div className="surface-heatmap__inspector-logs">
                  <span>Telemetry Output:</span>
                  <pre>{selectedPoint.stdout || selectedPoint.stderr || '(No raw telemetry output)'}</pre>
                </div>
              </div>
            )}
          </div>

          {/* Feature 2: Differential Runtime Blame */}
          {surfaceResult.blame && (
            <div className="surface-heatmap__blame-card">
              <div className="surface-heatmap__blame-badge">Differential Runtime Blame</div>
              <h4 className="surface-heatmap__blame-heading">
                Culprit Code Isolation: <code>{surfaceResult.blame.culpable_file}:{surfaceResult.blame.culpable_line}</code>
              </h4>
              <div className="surface-heatmap__blame-traces">
                {surfaceResult.blame.pass_trace && (
                  <div className="blame-trace blame-trace--pass">
                    <span className="blame-tag blame-tag--pass">PASS</span>
                    <code>{surfaceResult.blame.pass_trace.summary_line}</code>
                  </div>
                )}
                {surfaceResult.blame.fail_trace && (
                  <div className="blame-trace blame-trace--fail">
                    <span className="blame-tag blame-tag--fail">FAIL</span>
                    <code>{surfaceResult.blame.fail_trace.summary_line}</code>
                  </div>
                )}
              </div>
              {surfaceResult.blame.culpable_code && (
                <div className="surface-heatmap__blame-code">
                  <div className="blame-code-header">Divergent Source Code:</div>
                  <pre>
                    <code>{surfaceResult.blame.culpable_code}</code>
                  </pre>
                </div>
              )}
              <div className="surface-heatmap__blame-explanation">
                <strong>Analytical Diagnosis:</strong> {surfaceResult.blame.explanation}
              </div>
              {surfaceResult.blame.suggested_fix && (
                <div className="surface-heatmap__blame-fix">
                  <strong>Recommended Fix:</strong> {surfaceResult.blame.suggested_fix}
                </div>
              )}
            </div>
          )}

          {/* Feature 3: Executable Invariant Exporter */}
          {exportResult && (
            <div className="surface-heatmap__export-box">
              <div className="export-box__header">
                <div>
                  <span className="export-box__badge">CI/CD Guardrail</span>
                  <h4 className="export-box__filename">{exportResult.filename}</h4>
                </div>
                <div className="export-box__btns">
                  <button className="export-box__btn" onClick={handleCopyCode}>
                    {copied ? '✓ Copied' : 'Copy Test Code'}
                  </button>
                  <button className="export-box__btn export-box__btn--primary" onClick={handleDownloadFile}>
                    Download .py
                  </button>
                </div>
              </div>
              <pre className="export-box__code">
                <code>{exportResult.code}</code>
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
