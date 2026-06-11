import { lazy, Suspense, useCallback, useState } from 'react';
import UploadZone from './components/UploadZone.jsx';
import AgentLane from './components/AgentLane.jsx';
import PacketView from './components/PacketView.jsx';
import TracePanel from './components/TracePanel.jsx';

// pdf.js viewer is heavy (~1MB) — load it only when a citation source is opened.
const SourceViewer = lazy(() => import('./components/SourceViewer.jsx'));

const INITIAL_LANES = { classifier: 'idle', researcher: 'idle', drafter: 'idle' };

export default function App() {
  const [lanes, setLanes] = useState(INITIAL_LANES);
  const [classified, setClassified] = useState(null);
  const [legal, setLegal] = useState(null);
  const [packet, setPacket] = useState(null);
  const [approved, setApproved] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [trace, setTrace] = useState({});
  const [viewerSource, setViewerSource] = useState(null);  // {docKey, page, query} | null

  const reset = () => {
    setLanes(INITIAL_LANES);
    setClassified(null);
    setLegal(null);
    setPacket(null);
    setApproved(false);
    setError(null);
    setTrace({});
  };

  const runPipeline = useCallback(async (noticeText, language = 'en') => {
    reset();
    setRunning(true);
    setLanes({ classifier: 'running', researcher: 'idle', drafter: 'idle' });

    try {
      const response = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: noticeText, language }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`API error ${response.status}: ${detail}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') { setRunning(false); return; }

          let event;
          try { event = JSON.parse(raw); } catch { continue; }

          if (event.meta && event.stage) {
            setTrace((prev) => ({ ...prev, [event.stage]: event.meta }));
          }

          if (event.stage === 'classifier') {
            setClassified(event.data);
            setLanes({ classifier: 'done', researcher: 'running', drafter: 'idle' });
          } else if (event.stage === 'researcher') {
            setLegal(event.data);
            setLanes({ classifier: 'done', researcher: 'done', drafter: 'running' });
          } else if (event.stage === 'drafter') {
            setPacket(event.data);
            setLanes({ classifier: 'done', researcher: 'done', drafter: 'done' });
            setRunning(false);
          } else if (event.stage === 'error') {
            throw new Error(event.message ?? 'Pipeline error');
          }
        }
      }
    } catch (err) {
      setError(err.message);
      setLanes(INITIAL_LANES);
    } finally {
      setRunning(false);
    }
  }, []);

  const connectorActive = (from) =>
    from === 'classifier' ? lanes.classifier === 'done' :
    from === 'researcher' ? lanes.researcher === 'done' : false;

  return (
    <div className="app-shell">
      {/* Header */}
      <header className="app-header">
        <div className="header-brand">
          <div className="header-logo">NF</div>
          <span className="header-name">NoticeFlow</span>
          <span className="header-tag">Multi-Agent GST Response System</span>
        </div>
        <div className="header-pills">
          <span className="tech-pill">Google ADK</span>
          <span className="tech-pill">Vertex AI</span>
          <span className="tech-pill">MCP</span>
          <span className="tech-pill">Vertex AI Search</span>
        </div>
      </header>

      {/* Main */}
      <main className="app-main">
        {/* Upload */}
        <section className="upload-section">
          <div className="section-label">Notice Input</div>
          <UploadZone onNoticeText={runPipeline} disabled={running} />
        </section>

        {/* Error */}
        {error && (
          <div className="error-banner">
            ⚠ {error}
            <button
              onClick={reset}
              style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--danger)', fontWeight: 600 }}
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Pipeline */}
        <section className="pipeline-section">
          <div className="section-label">Pipeline</div>
          <div className="pipeline-lanes">
            <AgentLane agent="classifier" state={lanes.classifier} data={classified} />

            <div className="pipeline-connector">
              <div className={`connector-line ${connectorActive('classifier') ? 'active' : ''}`}>
                ——→
              </div>
            </div>

            <AgentLane agent="researcher" state={lanes.researcher} data={legal} />

            <div className="pipeline-connector">
              <div className={`connector-line ${connectorActive('researcher') ? 'active' : ''}`}>
                ——→
              </div>
            </div>

            <AgentLane agent="drafter" state={lanes.drafter} data={packet} />
          </div>
        </section>

        {/* Execution trace (#3.9) — read-only per-agent observability */}
        {Object.keys(trace).length > 0 && <TracePanel trace={trace} />}

        {/* Packet */}
        {packet && (
          <PacketView
            packet={packet}
            approved={approved}
            onApprove={() => setApproved(true)}
            onViewSource={setViewerSource}
          />
        )}
      </main>

      {/* In-app source-PDF viewer (lazy) — opens when a citation source is clicked */}
      {viewerSource && (
        <Suspense fallback={null}>
          <SourceViewer {...viewerSource} onClose={() => setViewerSource(null)} />
        </Suspense>
      )}
    </div>
  );
}
