/** Dashboard automático: KPIs, filtros, gráficos, tabla y preguntas en lenguaje natural. */
import * as api from '../api.js';
import { withWorkspace } from '../api.js';
import * as charts from '../charts.js';
import { t, num, pct, dec } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import { el, clear, table, badge, note, emptyState, fail, toast, jobPanel, icon } from '../ui.js';

let nav = null;
let spec = null;
let activeFilters = {};

function fmtKpi(k) {
  const v = k.value;
  if (v == null || !isFinite(v)) return '—';
  if (k.format === 'percent') return pct(v, 1, true);
  if (k.format === 'percent_unit') return pct(v, 1);
  if (k.format === 'money') return num(v, 0);
  return num(v, Math.abs(v) < 100 && v % 1 !== 0 ? 2 : 0);
}

function kpiTiles(kpis) {
  return el('div', { class: 'grid grid-4 mb-2' }, ...kpis.map((k) => {
    const delta = k.delta_pct;
    const kind = delta == null ? '' : (delta >= 0 ? 'ok' : 'bad');
    return el('div', { class: `stat ${kind}` },
      el('div', { class: 'stat-label', text: k.kind === 'rows' ? t('dash.records') : k.label }),
      el('div', { class: 'stat-value', text: fmtKpi(k) }),
      delta != null ? el('div', { class: `stat-sub ${delta >= 0 ? 'text-ok' : 'text-bad'}`,
        text: `${delta >= 0 ? '+' : ''}${dec(delta, 1)}% ${t('dash.vs_prev')} (${k.delta_period || ''})` }) : null);
  }));
}

function filterBar(onApply) {
  const bar = el('div', { class: 'row', style: 'align-items:flex-end' });
  (spec.filters || []).forEach((f) => {
    if (f.type === 'daterange') {
      const desde = el('input', { type: 'date', value: (activeFilters[f.column]?.from) || '' });
      const hasta = el('input', { type: 'date', value: (activeFilters[f.column]?.to) || '' });
      const setr = () => {
        if (desde.value || hasta.value) activeFilters[f.column] = { from: desde.value || null, to: hasta.value || null };
        else delete activeFilters[f.column];
      };
      desde.onchange = setr; hasta.onchange = setr;
      bar.appendChild(el('div', { class: 'field mb-0' },
        el('label', { text: `${f.column} · ${t('dash.from')}` }), desde));
      bar.appendChild(el('div', { class: 'field mb-0' },
        el('label', { text: t('dash.to') }), hasta));
    } else {
      const sel = el('select', { multiple: true, size: '3', style: 'min-width:180px' },
        ...f.options.map((o) => el('option', {
          value: o, text: o, selected: (activeFilters[f.column] || []).includes(o) })));
      sel.onchange = () => {
        const vals = Array.from(sel.selectedOptions).map((o) => o.value);
        if (vals.length) activeFilters[f.column] = vals; else delete activeFilters[f.column];
      };
      bar.appendChild(el('div', { class: 'field mb-0' },
        el('label', { text: f.column }), sel));
    }
  });
  const aplicar = el('button', { class: 'btn btn-primary', onClick: onApply }, t('dash.refresh'));
  const limpiar = el('button', {
    class: 'btn btn-ghost',
    onClick: () => { activeFilters = {}; onApply(); },
  }, t('dash.clear_filters'));
  bar.appendChild(aplicar);
  bar.appendChild(limpiar);
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h3', { text: t('dash.filters') })), bar);
}

function chartCard(c) {
  const data = c.data || [];
  if (!data.length) return null;
  if (c.type === 'line') {
    return charts.line([data.map((p, i) => [i, p.y ?? 0])], {
      title: c.title, width: 520, height: 230,
      fmtX: (v) => (data[Math.round(v)]?.x || '').slice(2, 7),
      fmtY: (v) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(0)}M` : v.toFixed(0)),
    });
  }
  if (c.type === 'bars') {
    return charts.hbars(data.map((p) => ({ label: p.x, value: p.y ?? 0 })), {
      title: c.title, width: 520, maxItems: 12,
      fmt: (v) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : num(v, 0)),
    });
  }
  return charts.histogram(data.map((p) => ({ from: p.x, to: p.x, count: p.y })), {
    title: c.title, width: 520, height: 190,
  });
}

/* ── preguntale a tus datos ──────────────────────────────────────────────── */
function askPanel(datasetId) {
  const input = el('input', { type: 'text', style: 'font-size:14.5px' });
  input.placeholder = t('dash.ask_placeholder');
  const micBtn = el('button', { class: 'btn btn-icon' }, icon('mic'));
  const send = el('button', { class: 'btn btn-primary' }, t('dash.ask_send'));
  const out = el('div', { class: 'mt-2' });

  micBtn.onclick = () => {
    if (!audio.dictationSupported()) { toast(t('audio.voice_unsupported'), 'warn'); return; }
    micBtn.classList.add('btn-primary');
    audio.dictate({
      onResult: (text) => { input.value = text; },
      onEnd: () => micBtn.classList.remove('btn-primary'),
      onError: () => micBtn.classList.remove('btn-primary'),
    });
  };

  async function preguntar() {
    const q = input.value.trim();
    if (!q) return;
    send.disabled = true;
    clear(out).appendChild(el('div', { class: 'row' }, el('span', { class: 'spinner' })));
    try {
      const lang = document.documentElement.lang || 'es';
      // la pregunta viaja con los filtros puestos: si el tablero muestra dos
      // sucursales, la respuesta tiene que hablar de esas dos
      const r = await api.post('/api/ai/ask',
        { dataset_id: datasetId, question: q, lang, filters: activeFilters });
      clear(out);
      out.appendChild(el('div', { class: 'note accent' },
        el('div', { class: 'row row-tight mb-1' },
          badge(`${t('dash.ask_engine')}: ${r.engine}`, 'accent')),
        el('div', { text: r.answer })));
      if (r.note) out.appendChild(note(r.note, 'warn'));
      if (r.rows?.length) {
        out.appendChild(table(r.columns.map((c) => ({ key: c, label: c })), r.rows,
          { compact: true, maxHeight: '260px' }));
      }
      out.appendChild(el('details', { class: 'mt-1' },
        el('summary', { class: 'small muted', style: 'cursor:pointer', text: t('dash.ask_sql') }),
        el('pre', { class: 'code mt-1', text: r.sql })));
      audio.speak(r.answer);
    } catch (err) {
      clear(out).appendChild(note(err.message, err.status === 422 ? 'warn' : 'bad'));
    } finally { send.disabled = false; }
  }
  send.onclick = preguntar;
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') preguntar(); });

  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('dash.ask_title') }),
        el('div', { class: 'card-sub', text: t('dash.ask_hint') }))),
    el('div', { class: 'row' },
      el('div', { style: 'flex:1;min-width:260px' }, input), micBtn, send),
    out);
}

export default {
  mount(host, { go }) { nav = go; this.host = host; },
  async refresh() {
    const host = this.host;
    const s = store.get();
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('dash.title') }),
      el('p', { class: 'page-lead', text: t('dash.lead') })));

    if (!s.datasetId) {
      host.appendChild(emptyState(t('dash.no_dataset')));
      host.appendChild(el('button', { class: 'btn btn-primary mt-2', onClick: () => nav('data') }, t('nav.data')));
      return;
    }

    const sel = el('select', { style: 'max-width:340px' },
      ...s.datasets.map((d) => el('option', {
        value: d.id, text: `${d.name} · ${num(d.rows)}`, selected: d.id === s.datasetId })));
    sel.onchange = () => { store.set({ datasetId: sel.value }); spec = null; activeFilters = {}; this.refresh(); };
    host.appendChild(el('div', { class: 'row mb-2' }, sel));

    const body = el('div');
    host.appendChild(body);
    const self = this;

    async function render() {
      clear(body).appendChild(el('div', { class: 'card' }, el('div', { class: 'row' },
        el('span', { class: 'spinner' }), el('span', { text: t('common.loading') }))));
      try {
        if (!spec || spec.dataset_id !== s.datasetId) {
          spec = await api.get(`/api/dashboards/${s.datasetId}/spec`);
          activeFilters = {};
        }
        const datos = await api.post(`/api/dashboards/${s.datasetId}/run`,
          { spec, filters: activeFilters });
        clear(body);
        body.appendChild(filterBar(render));
        body.appendChild(kpiTiles(datos.kpis));

        const grid = el('div', { class: 'grid grid-2 mb-2' });
        datos.charts.forEach((c) => { const ch = chartCard(c); if (ch) grid.appendChild(ch); });
        body.appendChild(grid);

        // exportación del estado filtrado
        const job = jobPanel(); job.root.classList.add('hidden');
        const mkExport = (fmt, label) => {
          const b = el('button', { class: 'btn' }, icon('download', 15), label);
          b.onclick = async () => {
            b.disabled = true; job.root.classList.remove('hidden'); job.reset();
            try {
              const r = await api.runJob(`/api/dashboards/${s.datasetId}/export`,
                { spec, filters: activeFilters, format: fmt }, (j) => job.update(j));
              toast(`${r.filename} · ${num(r.rows)} ${t('common.rows')}`, 'ok', t('common.success'));
              audio.beep('done');
              const a = el('a', { class: 'btn btn-primary btn-sm', href: withWorkspace(r.download_url), download: '' },
                t('common.download'));
              job.root.appendChild(a);
            } catch (err) { fail(err); } finally { b.disabled = false; }
          };
          return b;
        };
        body.appendChild(el('div', { class: 'card' },
          el('div', { class: 'row' }, mkExport('xlsx', t('dash.export_xlsx')),
            mkExport('csv', t('dash.export_csv'))), job.root));

        body.appendChild(el('div', { class: 'card' },
          el('div', { class: 'card-head' },
            el('div', {}, el('h3', { text: t('dash.table') }),
              el('div', { class: 'card-sub',
                text: `${t('dash.showing')} ${num(datos.table.rows.length)} ${t('common.of')} ${num(datos.table.total)}` }))),
          table(datos.table.columns.map((c) => ({ key: c, label: c })), datos.table.rows,
            { compact: true, maxHeight: '420px' })));

        if (spec.notes?.length) {
          body.appendChild(el('div', { class: 'card' },
            el('div', { class: 'card-head' }, el('h3', { text: t('dash.notes') })),
            ...spec.notes.map((n) => el('p', { class: 'small muted', text: n }))));
        }
        body.appendChild(askPanel(s.datasetId));
      } catch (err) { clear(body); fail(err); }
    }
    await render();
  },
};
