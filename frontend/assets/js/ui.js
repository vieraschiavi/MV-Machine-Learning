/** Primitivas de interfaz: DOM, avisos, tablas, iconos y bloques reutilizables. */
import { t, num, pct, dec, bytes, when } from './i18n.js';
import * as audio from './audio.js';

/* ── DOM ─────────────────────────────────────────────────────────────────── */
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => {
    if (v == null || v === false) return;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
    else node.setAttribute(k, v === true ? '' : v);
  });
  children.flat().forEach((c) => {
    if (c == null || c === false) return;
    node.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
  });
  return node;
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* ── iconos (trazo, sin emojis) ──────────────────────────────────────────── */
const PATHS = {
  overview: 'M3 3h7v7H3zM14 3h7v4h-7zM14 10h7v11h-7zM3 13h7v8H3z',
  data: 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  explore: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4',
  etl: 'M4 7h10M4 7l3-3M4 7l3 3M20 17H10M20 17l-3-3M20 17l-3 3',
  model: 'M12 3v4M12 17v4M3 12h4M17 12h4M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM6.5 6.5l2.5 2.5M15 15l2.5 2.5M17.5 6.5L15 9M9 15l-2.5 2.5',
  results: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  ai: 'M12 3a4 4 0 0 1 4 4v1a4 4 0 0 1 0 8v1a4 4 0 0 1-8 0v-1a4 4 0 0 1 0-8V7a4 4 0 0 1 4-4zM12 3v18',
  export: 'M12 3v12M12 3L8 7M12 3l4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',
  sun: 'M12 6a6 6 0 1 0 0 12 6 6 0 0 0 0-12zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z',
  volume: 'M11 5L6 9H3v6h3l5 4V5zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13',
  mute: 'M11 5L6 9H3v6h3l5 4V5zM22 9l-6 6M16 9l6 6',
  play: 'M6 4l14 8-14 8z',
  stop: 'M6 6h12v12H6z',
  mic: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3',
  check: 'M4 12l5 5L20 6',
  x: 'M6 6l12 12M18 6L6 18',
  trash: 'M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13',
  refresh: 'M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6',
  download: 'M12 3v12M12 15l-4-4M12 15l4-4M4 19h16',
  menu: 'M4 7h16M4 12h16M4 17h16',
  plus: 'M12 5v14M5 12h14',
  chevron: 'M9 6l6 6-6 6',
  warn: 'M12 3l9 17H3zM12 9v5M12 17v.5',
  info: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 11v5M12 8v.5',
  db: 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6',
  file: 'M6 3h7l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM13 3v5h5',
};

export function icon(name, size = 16) {
  const d = PATHS[name] || PATHS.info;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size); svg.setAttribute('height', size);
  svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.7');
  svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', d);
  svg.appendChild(p);
  return svg;
}

/* ── avisos ──────────────────────────────────────────────────────────────── */
let toastHost = null;
export function toast(text, kind = 'info', title = null, ms = 5200) {
  if (!toastHost) {
    toastHost = el('div', { class: 'toasts' });
    document.body.appendChild(toastHost);
  }
  const node = el('div', { class: `toast ${kind === 'info' ? '' : kind}` },
    title ? el('div', { class: 'toast-title', text: title }) : null,
    el('div', { class: 'toast-text', text: String(text).slice(0, 500) }));
  toastHost.appendChild(node);
  audio.beep(kind === 'bad' ? 'error' : (kind === 'ok' ? 'success' : (kind === 'warn' ? 'warn' : 'click')));
  setTimeout(() => {
    node.style.transition = 'opacity .25s, transform .25s';
    node.style.opacity = '0'; node.style.transform = 'translateX(14px)';
    setTimeout(() => node.remove(), 260);
  }, ms);
  return node;
}

export function fail(err) {
  const msg = err?.message === 'NETWORK' ? t('errors.network') : (err?.message || String(err));
  toast(msg, 'bad', t('common.error'), 8000);
  return msg;
}

/* ── modal ───────────────────────────────────────────────────────────────── */
export function modal({ title, body, actions = [], onClose } = {}) {
  const back = el('div', { class: 'modal-backdrop' });
  const box = el('div', { class: 'modal' },
    el('div', { class: 'modal-head' }, el('h2', { text: title || '' })),
    el('div', { class: 'modal-body' }, body),
    el('div', { class: 'modal-foot' },
      ...actions.map((a) => el('button', {
        class: `btn ${a.kind ? `btn-${a.kind}` : ''}`,
        onClick: () => { const r = a.onClick?.(); if (r !== false) close(); },
      }, a.label))));
  function close() { back.remove(); onClose?.(); }
  back.appendChild(box);
  back.addEventListener('click', (e) => { if (e.target === back) close(); });
  document.addEventListener('keydown', function esc2(e) {
    if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc2); }
  });
  document.body.appendChild(back);
  return { close, box };
}

export function confirmDialog(text, onYes) {
  modal({
    title: t('common.confirm'),
    body: el('p', { text }),
    actions: [
      { label: t('common.cancel'), kind: 'ghost' },
      { label: t('common.confirm'), kind: 'danger', onClick: onYes },
    ],
  });
}

/* ── bloques ─────────────────────────────────────────────────────────────── */
export function stat(label, value, sub, kind = '') {
  return el('div', { class: `stat ${kind}` },
    el('div', { class: 'stat-label', text: label }),
    el('div', { class: 'stat-value', text: value }),
    sub ? el('div', { class: 'stat-sub', text: sub }) : null);
}

export function badge(text, kind = '') {
  return el('span', { class: `badge ${kind}`, text });
}

export function note(text, kind = '') {
  return el('div', { class: `note ${kind}` }, text);
}

export function emptyState(title, sub) {
  return el('div', { class: 'empty-state' },
    el('div', { class: 'empty-title', text: title }),
    sub ? el('div', { class: 'small', text: sub }) : null);
}

/**
 * Tabla de datos. `columns` acepta {key, label, align, format, render, width}.
 */
export function table(columns, rows, { compact = false, maxHeight } = {}) {
  const wrap = el('div', { class: 'table-wrap' });
  if (maxHeight) wrap.style.maxHeight = maxHeight;
  const tbl = el('table', { class: compact ? 'table-compact' : '' });
  const thead = el('thead');
  const trh = el('tr');
  columns.forEach((c) => {
    const th = el('th', { class: c.align === 'right' ? 'num' : '', text: c.label });
    if (c.width) th.style.minWidth = c.width;
    trh.appendChild(th);
  });
  thead.appendChild(trh);
  const tbody = el('tbody');
  rows.forEach((r) => {
    const tr = el('tr');
    columns.forEach((c) => {
      const raw = typeof c.key === 'function' ? c.key(r) : r[c.key];
      const td = el('td', { class: [c.align === 'right' ? 'num' : '', c.mono ? 'mono' : ''].join(' ').trim() });
      if (c.render) {
        const out = c.render(raw, r);
        if (out instanceof Node) td.appendChild(out);
        else td.textContent = out ?? '';
      } else {
        td.textContent = c.format ? c.format(raw, r) : (raw ?? '');
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  tbl.appendChild(thead); tbl.appendChild(tbody);
  wrap.appendChild(tbl);
  return wrap;
}

/* ── panel de progreso de un trabajo ─────────────────────────────────────── */
export function jobPanel() {
  const bar = el('div', { class: 'progress-bar' });
  const msg = el('div', { class: 'small muted', style: 'margin-top:8px' });
  const log = el('div', { class: 'job-log mt-1' });
  const root = el('div', {}, el('div', { class: 'progress' }, bar), msg, log);
  let last = 0;
  return {
    root,
    update(job) {
      bar.style.width = `${Math.max(job.progress || 0, 2)}%`;
      bar.classList.toggle('done', job.status === 'terminado');
      bar.classList.toggle('fail', job.status === 'error');
      msg.textContent = `${job.progress?.toFixed(0) ?? 0}% · ${job.message || ''}`;
      const entries = job.log || [];
      if (entries.length !== last) {
        last = entries.length;
        clear(log);
        entries.slice(-60).forEach((e) => log.appendChild(el('div', { text: e.text })));
        log.scrollTop = log.scrollHeight;
      }
    },
    reset() { bar.style.width = '0'; bar.className = 'progress-bar'; msg.textContent = ''; clear(log); last = 0; },
  };
}

/* ── formato ─────────────────────────────────────────────────────────────── */
export { num, pct, dec, bytes, when };

export function metricValue(name, v) {
  if (v == null || !isFinite(v)) return '—';
  const asPct = ['accuracy', 'balanced_accuracy', 'precision', 'recall', 'mape', 'wmape',
    'smape', 'bias', 'positive_rate'];
  if (asPct.includes(name)) return pct(v, 1);
  if (name === 'lift_10') return `${dec(v, 2)}x`;
  return dec(v, 4);
}

export function severityKind(level) {
  return { high: 'bad', medium: 'warn', low: '', ok: 'ok', revisar: 'warn', alerta: 'bad', info: '' }[level] || '';
}
