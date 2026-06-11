import { useEffect, useRef, useState } from 'react';
import { shortCitation } from '../utils.js';

export default function CitationChip({ citation, onViewSource }) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const keyHandler = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', handler);
    document.addEventListener('keydown', keyHandler);
    return () => {
      document.removeEventListener('mousedown', handler);
      document.removeEventListener('keydown', keyHandler);
    };
  }, [open]);

  return (
    <span ref={wrapperRef} className="citation-chip-wrapper">
      <button
        className="citation-chip"
        onClick={() => setOpen((o) => !o)}
        title={citation.source_id}
      >
        {shortCitation(citation.source_id)}
      </button>

      {open && (
        <div className="citation-popover" role="tooltip">
          <div className="popover-source-id">{citation.source_id}</div>
          {citation.snippet && (
            <div className="popover-snippet">
              &ldquo;{citation.snippet}&rdquo;
            </div>
          )}
          {citation.relevance_note && (
            <div className="popover-relevance">{citation.relevance_note}</div>
          )}
          {citation.source_doc && onViewSource && (
            <button
              className="popover-source-btn"
              onClick={() => {
                setOpen(false);
                onViewSource({
                  docKey: citation.source_doc,
                  page: citation.source_page,
                  query: citation.snippet,
                });
              }}
            >
              View in source PDF ↗
            </button>
          )}
        </div>
      )}
    </span>
  );
}
