/* #3.9 — Observability trace. Read-only display of per-agent execution metadata
 * the pipeline already emits (timing, model, integer counts). No agent logic,
 * no retrieved legal text — only primitives streamed in each event's `meta`. */
import { LANG_LABELS } from '../utils.js';

const STAGES = [
  { key: 'classifier', step: '①', label: 'Classifier' },
  { key: 'researcher', step: '②', label: 'Researcher' },
  { key: 'drafter',    step: '③', label: 'Drafter' },
];

function ms(v) {
  if (v == null) return '—';
  return v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${v} ms`;
}

export default function TracePanel({ trace }) {
  const rows = STAGES.filter((s) => trace[s.key]).map((s) => ({ ...s, meta: trace[s.key] }));
  if (rows.length === 0) return null;

  const total = rows.reduce((sum, r) => sum + (r.meta.elapsed_ms ?? 0), 0);

  return (
    <section className="trace-section">
      <details className="trace-panel">
        <summary className="trace-summary">
          <span className="section-label" style={{ margin: 0 }}>Execution Trace</span>
          <span className="trace-total">{ms(total)} total · {rows.length} agents</span>
        </summary>

        <table className="trace-table">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Model</th>
              <th style={{ textAlign: 'right' }}>Time</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td>{r.step} {r.label}</td>
                <td className="mono">{r.meta.model ?? '—'}</td>
                <td style={{ textAlign: 'right' }}>{ms(r.meta.elapsed_ms)}</td>
                <td className="trace-detail">
                  {r.key === 'researcher' && (
                    <>
                      {r.meta.citations ?? 0} citations ·{' '}
                      {r.meta.evidence_chunks ?? 0} grounding chunks
                    </>
                  )}
                  {r.key === 'drafter' && r.meta.language && (
                    <>output: {LANG_LABELS[r.meta.language] ?? r.meta.language}</>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
