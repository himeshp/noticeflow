/** Indian numbering format: ₹1,05,900 (lakh system) */
export function formatINR(amount) {
  if (amount == null || isNaN(amount)) return '—';
  const num = Math.round(amount);
  if (num === 0) return '₹0';
  const str = num.toString();
  if (str.length <= 3) return `₹${str}`;
  const last3 = str.slice(-3);
  const rest = str.slice(0, -3);
  const formatted = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',');
  return `₹${formatted},${last3}`;
}

/** Format ISO date string for display */
export function formatDate(dateStr) {
  if (!dateStr) return '—';
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

/** Days until deadline (negative = overdue) */
export function daysUntil(dateStr) {
  if (!dateStr) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const deadline = new Date(dateStr + 'T00:00:00');
  return Math.round((deadline - today) / (1000 * 60 * 60 * 24));
}

/** Urgency tier from a deadline (mirrors src/noticeflow/deadlines.py thresholds:
 *  <0 overdue · 0-7 critical · 8-14 soon · >14 normal · no date → none) */
export function urgencyTier(dateStr) {
  const d = daysUntil(dateStr);
  if (d === null) return 'NONE';
  if (d < 0) return 'OVERDUE';
  if (d <= 7) return 'CRITICAL';
  if (d <= 14) return 'SOON';
  return 'NORMAL';
}

/** Per-tier display metadata: short label + css modifier class */
export const URGENCY_META = {
  OVERDUE:  { label: 'Overdue',              cls: 'overdue'  },
  CRITICAL: { label: 'Due within a week',    cls: 'critical' },
  SOON:     { label: 'Due within two weeks', cls: 'soon'     },
  NORMAL:   { label: 'On schedule',          cls: 'normal'   },
  NONE:     { label: 'No deadline',          cls: 'none'     },
};

/** "Next action by 14 Jun 2026 — 5 days remaining" (null when no deadline) */
export function nextActionLine(dateStr) {
  if (!dateStr) return null;
  const d = daysUntil(dateStr);
  const when = formatDate(dateStr);
  if (d < 0) return `Reply was due ${when} — ${Math.abs(d)} day${Math.abs(d) !== 1 ? 's' : ''} overdue`;
  if (d === 0) return `Next action by ${when} — due today`;
  return `Next action by ${when} — ${d} day${d !== 1 ? 's' : ''} remaining`;
}

/** Source-PDF display labels (in-app pdf.js viewer) */
export const DOC_LABELS = {
  cgst_act_2017: 'CGST Act, 2017',
  cgst_rules_2017: 'CGST Rules, 2017',
  circular_31_2018: 'Circular 31/2018-GST',
  circular_135_2020: 'Circular 135/2020-GST',
  circular_183_2022: 'Circular 183/2022-GST',
};

/** Reply-language display labels (#3.7) */
export const LANG_LABELS = {
  en: 'English',
  hi: 'हिंदी',
  bilingual: 'Both',
};

/** Notice type display label */
export const NOTICE_LABELS = {
  DRC_01: 'DRC-01',
  ASMT_10: 'ASMT-10',
  ITC_MISMATCH: 'ITC Mismatch',
  UNKNOWN: 'Unknown',
};

/** The statutory reply FORM each notice type maps to (matches forms/generator.py) */
export const FORM_CODES = {
  DRC_01: 'DRC-06',
  ASMT_10: 'ASMT-11',
  ITC_MISMATCH: 'DRC-01C',
  UNKNOWN: 'Reply',
};

/** Short label for a citation source_id */
export function shortCitation(sourceId) {
  return sourceId
    .replace('CGST Act 2017, ', '')
    .replace('CGST Rules 2017, ', '')
    .replace('Circular ', 'Circ. ');
}
