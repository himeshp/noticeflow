import { useRef, useState } from 'react';
import { LANG_LABELS } from '../utils.js';

const SAMPLES = [
  { key: 'drc01',       label: 'DRC-01',      desc: 'Show-cause / demand notice' },
  { key: 'asmt10',      label: 'ASMT-10',     desc: 'Scrutiny notice' },
  // demoLang: if the language toggle is still at its default (English), this sample
  // runs bilingual so the Hindi/vernacular feature shows without touching the toggle.
  { key: 'itc_mismatch',label: 'ITC Mismatch', desc: 'GSTR-2B vs 3B dispute · bilingual demo', demoLang: 'bilingual' },
];

const LANGUAGES = ['en', 'hi', 'bilingual'];

export default function UploadZone({ onNoticeText, disabled }) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(null);
  const [language, setLanguage] = useState('en');
  const fileInputRef = useRef(null);

  const handleSample = async (key) => {
    setLoading(key);
    try {
      const res = await fetch(`/api/samples/${key}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const { text } = await res.json();
      // A sample's demoLang only kicks in if the user hasn't chosen a language
      // (toggle still at default English); an explicit choice is always honored.
      const sample = SAMPLES.find((s) => s.key === key);
      const lang = sample?.demoLang && language === 'en' ? sample.demoLang : language;
      if (lang !== language) setLanguage(lang);
      onNoticeText(text, lang);
    } catch (e) {
      alert(`Could not load sample: ${e.message}`);
    } finally {
      setLoading(null);
    }
  };

  const readFile = (file) => {
    const reader = new FileReader();
    reader.onload = (e) => onNoticeText(e.target.result, language);
    reader.readAsText(file, 'utf-8');
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) readFile(file);
  };

  return (
    <div
      className={`upload-zone ${dragging ? 'dragging' : ''} ${disabled ? 'disabled' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && fileInputRef.current?.click()}
      style={{ cursor: disabled ? 'default' : 'pointer' }}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".txt,.pdf"
        style={{ display: 'none' }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) readFile(f); }}
      />

      <div className="upload-icon">⬆</div>
      <div className="upload-text">
        Drop a GST notice (.txt or .pdf) or click to browse
      </div>

      <div className="upload-lang" onClick={(e) => e.stopPropagation()}>
        <span className="sample-label">Reply language:</span>
        {LANGUAGES.map((lng) => (
          <button
            key={lng}
            className={`lang-btn ${language === lng ? 'active' : ''}`}
            disabled={disabled}
            onClick={() => setLanguage(lng)}
            aria-pressed={language === lng}
          >
            {LANG_LABELS[lng]}
          </button>
        ))}
      </div>

      <div className="upload-samples" onClick={(e) => e.stopPropagation()}>
        <span className="sample-label">Try a sample:</span>
        {SAMPLES.map(({ key, label }) => (
          <button
            key={key}
            className="sample-btn"
            disabled={disabled || loading !== null}
            onClick={() => handleSample(key)}
            title={SAMPLES.find(s => s.key === key)?.desc}
          >
            {loading === key ? '…' : label}
          </button>
        ))}
      </div>
    </div>
  );
}
