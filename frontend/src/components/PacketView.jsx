import CitationChip from './CitationChip.jsx';
import {
  formatDate, formatINR, FORM_CODES, NOTICE_LABELS,
  urgencyTier, URGENCY_META, nextActionLine, LANG_LABELS,
} from '../utils.js';

async function downloadForm(packet) {
  const res = await fetch('/api/form', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(packet),
  });
  if (!res.ok) return;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const cd = res.headers.get('Content-Disposition') || '';
  const m = cd.match(/filename="?([^"]+)"?/);
  const a = document.createElement('a');
  a.href = url;
  a.download = m ? m[1] : 'gst_reply.pdf';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function AnnexureTable({ annexure }) {
  if (!annexure) return null;
  // Notice-type-aware (#FIX2): ASMT-10 is a GSTR-1 vs GSTR-3B turnover discrepancy,
  // so it shows an outward-supply table — not ITC rows.
  const isTurnover = annexure.recon_type === 'TURNOVER' || annexure.gstr1_outward_tax != null;
  const rows = isTurnover ? [
    { label: 'Outward Tax as per GSTR-1',               value: annexure.gstr1_outward_tax,     highlight: false },
    { label: 'Outward Tax as per GSTR-3B (Table 3.1)',  value: annexure.gstr3b_outward_tax,    highlight: false },
    { label: 'Difference (under-declared in GSTR-3B)',  value: annexure.outward_tax_difference, highlight: true  },
    { label: 'Total Output Tax Liability',              value: annexure.output_tax_liability,  highlight: false },
  ] : [
    { label: 'GSTR-3B Tax Paid',       value: annexure.gstr3b_tax_paid,      highlight: false },
    { label: 'GSTR-2B ITC Available',  value: annexure.gstr2b_itc_available, highlight: false },
    { label: 'GSTR-3B ITC Claimed',    value: annexure.gstr3b_itc_claimed,   highlight: false },
    { label: 'ITC Mismatch',           value: annexure.itc_mismatch_amount,  highlight: true  },
    { label: 'Output Tax Liability',   value: annexure.output_tax_liability,  highlight: false },
  ];

  return (
    <div>
      <table className="annexure-table">
        <thead>
          <tr>
            <th>Particulars</th>
            <th style={{ textAlign: 'right' }}>Amount</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, value, highlight }) => (
            <tr key={label} className={highlight ? 'highlight' : ''}>
              <td>{label}</td>
              <td>{formatINR(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {annexure.notes && (
        <p className="annexure-note">Note: {annexure.notes}</p>
      )}
    </div>
  );
}

export default function PacketView({ packet, approved, onApprove, onViewSource }) {
  if (!packet) return null;

  const tier = packet.response_deadline ? urgencyTier(packet.response_deadline) : null;
  const tierMeta = tier ? URGENCY_META[tier] : null;
  const nextAction = nextActionLine(packet.response_deadline);

  // #3.7 — prefer the localized prose for display; English stays canonical
  // (the form download always uses the English fields).
  const localized = packet.language && packet.language !== 'en';
  const legalBasisText = (localized && packet.legal_basis_localized) || packet.legal_basis;
  const replyText = (localized && packet.reply_body_localized) || packet.reply_body;
  const proseClass = localized ? ' lang-localized' : '';

  return (
    <div className="packet-section">
      <div className="packet-header-row">
        <span className="section-label">Response Packet</span>
        <div className="packet-actions">
          {approved && (
            <button className="download-btn" onClick={() => downloadForm(packet)}>
              ⬇ Download FORM {FORM_CODES[packet.notice_type] ?? 'Reply'} (draft PDF)
            </button>
          )}
          <button
            className={`approve-btn ${approved ? 'approved' : 'pending'}`}
            onClick={!approved ? onApprove : undefined}
            disabled={approved}
          >
            {approved ? '✓ Approved' : '✓ Approve for Filing'}
          </button>
        </div>
      </div>

      <div className="packet-card">
        {/* Human-escalation banner (#3.8) — low classification confidence */}
        {packet.reviewer_status === 'NEEDS_HUMAN' && packet.escalation_reason && (
          <div className="escalation-banner">
            ⚠ Needs human review — {packet.escalation_reason}
          </div>
        )}

        {/* Document header */}
        <div className="packet-doc-header">
          <div className="packet-ref">
            {packet.reference_number && `Re: SCN ${packet.reference_number}`}
            {packet.reference_number && packet.gstin && ' · '}
            {packet.gstin && `GSTIN ${packet.gstin}`}
          </div>

          <div className="packet-title">
            Reply to {NOTICE_LABELS[packet.notice_type] ?? packet.notice_type} — {packet.tax_period}
            {localized && (
              <span className="lang-chip" title="Reply shown in the selected language; the filing form stays English">
                भाषा / {LANG_LABELS[packet.language] ?? packet.language}
              </span>
            )}
          </div>

          {/* #2.6 — tiered deadline urgency + next-action line */}
          {tierMeta && nextAction && (
            <div className={`urgency-banner urgency-${tierMeta.cls}`}>
              <span className="urgency-tag">{tierMeta.label}</span>
              <span className="urgency-action">{nextAction}</span>
            </div>
          )}

          <div className="packet-meta">
            {packet.gstin && (
              <div className="meta-item">
                <span className="meta-label">GSTIN</span>
                <span className="meta-value">{packet.gstin}</span>
              </div>
            )}
            {packet.tax_period && (
              <div className="meta-item">
                <span className="meta-label">Tax Period</span>
                <span className="meta-value">{packet.tax_period}</span>
              </div>
            )}
            {packet.response_deadline && (
              <div className="meta-item">
                <span className="meta-label">Deadline</span>
                <span className="meta-value">{formatDate(packet.response_deadline)}</span>
              </div>
            )}
          </div>
        </div>

        {/* Document body */}
        <div className="packet-body">
          {/* Legal basis */}
          {legalBasisText && (
            <div>
              <span className="packet-block-label">Legal Basis</span>
              <p className={`legal-basis-text${proseClass}`}>{legalBasisText}</p>
              {packet.citations?.length > 0 && (
                <div className="citations-chips-row">
                  {packet.citations.map((c, i) => (
                    <CitationChip key={i} citation={c} onViewSource={onViewSource} />
                  ))}
                </div>
              )}
              {packet.citation_verification && (
                <div className={`verify-badge ${packet.citation_verification.passed ? 'ok' : 'warn'}`}>
                  {packet.citation_verification.passed ? '✓' : '⚠'}{' '}
                  {packet.citation_verification.verified}/{packet.citation_verification.total_citations}{' '}
                  citations verified against retrieved law
                  {!packet.citation_verification.passed &&
                    packet.citation_verification.unverified?.length > 0 && (
                      <span className="verify-dropped">
                        {' '}· dropped: {packet.citation_verification.unverified.join(', ')}
                      </span>
                    )}
                </div>
              )}
            </div>
          )}

          {/* Reply body */}
          {replyText && (
            <div>
              <span className="packet-block-label">Reply</span>
              <pre className={`reply-body-text${proseClass}`}>{replyText}</pre>
            </div>
          )}

          {/* Annexure */}
          {packet.annexure && (
            <div>
              <span className="packet-block-label">Annexure — Reconciliation Statement</span>
              <AnnexureTable annexure={packet.annexure} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
