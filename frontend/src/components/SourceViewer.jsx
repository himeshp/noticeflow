/* In-app source-PDF viewer (pdf.js). Opens one of the bundled CBIC PDFs from our
 * same-origin /api/source/<docKey>, jumps to the cited page, and highlights the
 * cited passage via pdf.js's find controller. Lazy-loaded so pdf.js (~1MB) is a
 * separate chunk. All fetches are same-origin allow-listed keys (no external URLs). */
import { useEffect, useRef, useState } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import {
  EventBus,
  PDFLinkService,
  PDFFindController,
  PDFViewer,
} from 'pdfjs-dist/web/pdf_viewer.mjs';
import 'pdfjs-dist/web/pdf_viewer.css';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { DOC_LABELS } from '../utils.js';

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

/** A short, distinctive phrase from the snippet — long/▸truncated snippets don't
 *  match exactly, so search the first ~12 meaningful words. */
function searchQuery(snippet) {
  if (!snippet) return '';
  return snippet
    .replace(/[“”"'…]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 12)
    .join(' ');
}

export default function SourceViewer({ docKey, page, query, onClose }) {
  const containerRef = useRef(null);
  const viewerRef = useRef(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error

  useEffect(() => {
    const container = containerRef.current;
    const viewerEl = viewerRef.current;
    if (!container || !viewerEl) return;

    let cancelled = false;
    let pdfDoc = null;

    const eventBus = new EventBus();
    const linkService = new PDFLinkService({ eventBus });
    const findController = new PDFFindController({ eventBus, linkService });
    const pdfViewer = new PDFViewer({ container, viewer: viewerEl, eventBus, linkService, findController });
    linkService.setViewer(pdfViewer);

    eventBus.on('pagesinit', () => {
      pdfViewer.currentScaleValue = 'page-width';
      if (page && page > 1) pdfViewer.currentPageNumber = page;
    });

    eventBus.on('pagesloaded', () => {
      if (cancelled) return;
      setStatus('ready');
      const q = searchQuery(query);
      if (q) {
        eventBus.dispatch('find', {
          source: null, type: '', query: q,
          caseSensitive: false, entireWord: false,
          highlightAll: true, findPrevious: false, matchDiacritics: false,
        });
      }
    });

    pdfjsLib.getDocument(`/api/source/${encodeURIComponent(docKey)}`).promise
      .then((pdf) => {
        if (cancelled) { pdf.destroy?.(); return; }
        pdfDoc = pdf;
        pdfViewer.setDocument(pdf);
        linkService.setDocument(pdf, null);
      })
      .catch(() => { if (!cancelled) setStatus('error'); });

    return () => {
      cancelled = true;
      try { pdfDoc?.destroy?.(); } catch { /* noop */ }
    };
  }, [docKey, page, query]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="source-modal-backdrop" onClick={onClose}>
      <div className="source-modal" onClick={(e) => e.stopPropagation()}>
        <div className="source-modal-head">
          <span className="source-modal-title">
            {DOC_LABELS[docKey] ?? docKey}{page ? ` · p. ${page}` : ''}
          </span>
          <button className="source-modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="source-modal-body" ref={containerRef}>
          <div className="pdfViewer" ref={viewerRef} />
          {status === 'loading' && <div className="source-modal-status">Loading source PDF…</div>}
          {status === 'error' && (
            <div className="source-modal-status">Couldn’t load this source PDF.</div>
          )}
        </div>
      </div>
    </div>
  );
}
