import { formatDate, formatINR, NOTICE_LABELS } from '../utils.js';

function StatusIndicator({ state }) {
  if (state === 'done') return <span className="status-check">✓</span>;
  if (state === 'running') return <span className="status-dot running" />;
  return <span className="status-dot idle" />;
}

function StatusLabel({ state }) {
  if (state === 'done') return <span style={{ color: 'var(--success)', fontWeight: 600 }}>Done</span>;
  if (state === 'running') return <span style={{ color: 'var(--accent)' }}>Processing…</span>;
  return <span>Waiting</span>;
}

/* ── Classifier output ─────────────────────────────────────────────── */
function ClassifierContent({ data }) {
  const urgentDays = data.response_deadline
    ? Math.round((new Date(data.response_deadline + 'T00:00:00') - new Date()) / 86400000)
    : null;
  const isUrgent = urgentDays !== null && urgentDays <= 7;

  return (
    <div className="lane-content">
      <span className="notice-type-badge">{NOTICE_LABELS[data.notice_type] ?? data.notice_type}</span>

      {data.governing_sections?.length > 0 && (
        <div className="lane-field">
          <span className="lane-field-label">Sections</span>
          <div className="sections-list">
            {data.governing_sections.map((s) => (
              <span key={s} className="section-tag">{s}</span>
            ))}
          </div>
        </div>
      )}

      {data.demanded_amount != null && (
        <div className="lane-field">
          <span className="lane-field-label">Demand</span>
          <span className="lane-field-value amount">{formatINR(data.demanded_amount)}</span>
        </div>
      )}

      {data.response_deadline && (
        <div className="lane-field">
          <span className="lane-field-label">Deadline</span>
          <span className={`deadline-chip ${isUrgent ? 'urgent' : 'normal'}`}>
            {isUrgent && '⚠ '}
            {formatDate(data.response_deadline)}
            {urgentDays !== null && urgentDays >= 0 && ` · ${urgentDays}d`}
          </span>
        </div>
      )}

      {data.gstin && (
        <div className="lane-field">
          <span className="lane-field-label">GSTIN</span>
          <span className="lane-field-value mono">{data.gstin}</span>
        </div>
      )}

      <div className="lane-field">
        <span className="lane-field-label">Confidence</span>
        <div className="confidence-bar-wrapper">
          <div className="confidence-bar-track">
            <div
              className="confidence-bar-fill"
              style={{ width: `${Math.round((data.confidence ?? 0) * 100)}%` }}
            />
          </div>
          <span className="confidence-label">{Math.round((data.confidence ?? 0) * 100)}%</span>
        </div>
      </div>
    </div>
  );
}

/* ── Researcher output ─────────────────────────────────────────────── */
function ResearcherContent({ data }) {
  const citations = data.citations ?? [];
  return (
    <div className="lane-content">
      <div className="lane-field">
        <span className="lane-field-label">{citations.length} Citation{citations.length !== 1 ? 's' : ''} retrieved</span>
        <div className="citations-list">
          {citations.slice(0, 4).map((c, i) => (
            <div key={i} className="citation-row">
              <div style={{ flex: 1 }}>
                <div className="citation-row-id">{c.source_id}</div>
              </div>
              <span className="citation-row-type">{c.source_type}</span>
            </div>
          ))}
          {citations.length > 4 && (
            <div style={{ fontSize: '0.72rem', color: 'var(--text-subtle)', paddingLeft: 4 }}>
              +{citations.length - 4} more
            </div>
          )}
        </div>
      </div>

      {data.applicable_response_options?.length > 0 && (
        <div className="lane-field">
          <span className="lane-field-label">Response options</span>
          <span className="lane-field-value" style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
            {data.applicable_response_options.length} available
          </span>
        </div>
      )}
    </div>
  );
}

/* ── Drafter output ────────────────────────────────────────────────── */
function DrafterContent({ data }) {
  return (
    <div className="lane-content">
      <div className="drafter-ready">
        <span className="drafter-ready-icon">📄</span>
        <span>Packet ready</span>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-subtle)' }}>
          {data.citations?.length ?? 0} citation{(data.citations?.length ?? 0) !== 1 ? 's' : ''} · annexure populated
        </span>
      </div>
    </div>
  );
}

/* ── Lane shell ────────────────────────────────────────────────────── */
const STEP_LABELS = { classifier: '① CLASSIFIER', researcher: '② RESEARCHER', drafter: '③ DRAFTER' };

/* 1–2 line plain-language description of each agent's job (for judges). */
const AGENT_DESC = {
  classifier: 'Gemini Flash reads the notice and extracts its type, governing sections, GSTIN, tax period, demand, and deadline.',
  researcher: 'Gemini Flash retrieves the governing GST law from a Vertex AI Search corpus and returns cited, attributed passages.',
  drafter: 'Gemini Pro pulls reconciliation figures via an MCP tool, then composes the cited, filing-ready reply.',
};

export default function AgentLane({ agent, state, data }) {
  return (
    <div className={`agent-lane ${state}`}>
      <div className="lane-header">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <span className="lane-step">{agent === 'classifier' ? 'Step 1' : agent === 'researcher' ? 'Step 2' : 'Step 3'}</span>
          <span className="lane-name">{STEP_LABELS[agent]}</span>
        </div>
        <div className="lane-status">
          <StatusLabel state={state} />
          <StatusIndicator state={state} />
        </div>
      </div>

      <p className="lane-desc">{AGENT_DESC[agent]}</p>

      <div className="lane-body">
        {state === 'idle' && (
          <span className="lane-idle-msg">Waiting for previous stage</span>
        )}
        {state === 'running' && (
          <div className="lane-running-msg">
            <div className="spinner" />
            Running…
          </div>
        )}
        {state === 'done' && data && (
          agent === 'classifier' ? <ClassifierContent data={data} /> :
          agent === 'researcher' ? <ResearcherContent data={data} /> :
          <DrafterContent data={data} />
        )}
      </div>
    </div>
  );
}
