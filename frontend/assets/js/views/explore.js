/** Exploración: perfil por columna, calidad, correlaciones y consulta libre. */
import * as api from '../api.js';
import * as charts from '../charts.js';
import { t, num, pct, dec, bytes } from '../i18n.js';
import * as store from '../store.js';
import { el, clear, table, badge, note, emptyState, fail, toast, severityKind, icon } from '../ui.js';

let nav = null;
let tab = 'quality';

function datasetPicker(onChange) {
  const s = store.get();
  const sel = el('select', { style: 'max-width:340px' },
    ...s.datasets.map((d) => el('option', {
      value: d.id, text: `${d.name} · ${num(d.rows)} ${t('common.rows')}`, selected: d.id === s.datasetId,
    })));
  sel.onchange = () => { store.set({ datasetId: sel.value }); onChange(); };
  return sel;
}

function qualityPanel(prof) {
  const q = prof.quality;
  const kind = q.score >= 80 ? 'ok' : (q.score >= 55 ? 'warn' : 'bad');
  const box = el('div', {},
    el('div', { class: 'grid grid-4 mb-2' },
      el('div', { class: 'chart-box' },
        charts.gauge(q.score, { title: t('explore.quality_score'), max: 100, label: q.level, kind })),
      el('div', { class: 'stat' },
        el('div', { class: 'stat-label', text: t('common.rows') }),
        el('div', { class: 'stat-value', text: num(prof.rows) }),
        el('div', { class: 'stat-sub', text: bytes(prof.size_bytes) })),
      el('div', { class: 'stat' },
        el('div', { class: 'stat-label', text: t('common.columns') }),
        el('div', { class: 'stat-value', text: num(prof.n_columns) })),
      el('div', { class: `stat ${prof.duplicate_row_groups ? 'warn' : 'ok'}` },
        el('div', { class: 'stat-label', text: t('explore.duplicate_rows') }),
        el('div', { class: 'stat-value', text: num(prof.duplicate_row_groups) }))),
  );
  if (!q.issues.length) {
    box.appendChild(note(t('etl.leakage_none'), 'ok'));
  } else {
    box.appendChild(table([
      { key: 'severity', label: t('common.status'), render: (v) => badge(t(`explore.severity_${v}`), severityKind(v)) },
      { key: 'column', label: t('common.column'), mono: true },
      { key: 'detail', label: t('common.detail') },
    ], q.issues, { maxHeight: '480px' }));
  }
  return box;
}

function columnCard(c) {
  const st = c.stats || {};
  const body = el('div', {});
  body.appendChild(el('div', { class: 'row row-tight mb-1' },
    badge(t(`explore.kind_${c.kind}`), c.kind === 'numeric' ? 'accent' : ''),
    c.constant ? badge('constante', 'bad') : null,
    c.unique_key ? badge('identificador', 'warn') : null));
  const kv = el('dl', { class: 'kv small' });
  const add = (k, v) => { kv.appendChild(el('dt', { text: k })); kv.appendChild(el('dd', { text: v })); };
  add(t('explore.nulls'), `${num(c.nulls)} (${pct(c.null_pct, 1, true)})`);
  add(t('explore.distinct'), num(c.distinct));
  if (c.kind === 'numeric') {
    add(t('explore.mean'), dec(st.mean, 2));
    add(t('explore.median'), dec(st.median, 2));
    add(t('explore.std'), dec(st.std, 2));
    add(`${t('explore.min')} / ${t('explore.max')}`, `${dec(st.min, 2)} / ${dec(st.max, 2)}`);
    if (st.outlier_pct != null) add(t('explore.outliers'), pct(st.outlier_pct, 1, true));
  }
  if (c.kind === 'datetime') { add(t('explore.min'), st.min || '—'); add(t('explore.max'), st.max || '—'); }
  body.appendChild(kv);
  if (c.histogram?.length) {
    body.appendChild(charts.histogram(c.histogram, { title: t('explore.distribution'), width: 420, height: 150 }));
  } else if (c.top_values?.length) {
    body.appendChild(charts.hbars(
      c.top_values.map((v) => ({ label: v.value, value: v.count })),
      { title: t('explore.top_values'), width: 420, maxItems: 8, fmt: (v) => num(v) }));
  }
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h3', { class: 'mono', text: c.name })), body);
}

function correlationsPanel(corr) {
  if (!corr.columns.length) return note(t('explore.no_correlations'), 'warn');
  return el('div', {},
    charts.heatmap(corr.columns, corr.pearson, { title: t('explore.correlations'), width: 640 }),
    el('h3', { class: 'mt-3 mb-1', text: t('explore.strongest_pairs') }),
    table([
      { key: 'a', label: 'A', mono: true }, { key: 'b', label: 'B', mono: true },
      { key: 'pearson', label: 'Pearson', align: 'right', format: (v) => dec(v, 4) },
      { key: 'spearman', label: 'Spearman', align: 'right', format: (v) => dec(v, 4) },
    ], corr.top_pairs, { maxHeight: '340px' }));
}

function sqlPanel(datasetId) {
  const box = el('textarea', { class: 'mono', rows: '4', value: 'SELECT * FROM {t} LIMIT 100' });
  const out = el('div', { class: 'mt-2' });
  const btn = el('button', { class: 'btn btn-primary' }, t('explore.run_query'));
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      const sql = box.value.replace(/\{t\}/g, '{t}');
      const r = await api.post(`/api/datasets/${datasetId}/query`,
        { sql: sql.replace(/\{t\}/g, `(SELECT * FROM {t})`), limit: 500 });
      clear(out).appendChild(table(r.columns.map((c) => ({ key: c, label: c })), r.rows,
        { compact: true, maxHeight: '460px' }));
    } catch (err) { clear(out).appendChild(note(err.message, 'bad')); } finally { btn.disabled = false; }
  };
  return el('div', {},
    el('div', { class: 'field' },
      el('label', { text: t('explore.sql') }), box,
      el('div', { class: 'hint', text: '{t} apunta al dataset seleccionado. Sólo SELECT y WITH.' })),
    btn, out);
}

export default {
  mount(host, { go }) { nav = go; this.host = host; },
  async refresh() {
    const host = this.host;
    const s = store.get();
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('explore.title') }),
      el('p', { class: 'page-lead', text: t('explore.lead') })));

    if (!s.datasetId) {
      host.appendChild(emptyState(t('errors.no_dataset'), t('data.lead')));
      host.appendChild(el('button', { class: 'btn btn-primary mt-2', onClick: () => nav('data') }, t('nav.data')));
      return;
    }

    host.appendChild(el('div', { class: 'row mb-2' }, datasetPicker(() => this.refresh())));
    const loading = el('div', { class: 'card' }, el('div', { class: 'row' },
      el('span', { class: 'spinner' }), el('span', { text: t('common.loading') })));
    host.appendChild(loading);

    let prof;
    try { prof = await store.loadProfile(true); } catch (err) { loading.remove(); fail(err); return; }
    loading.remove();

    const tabs = el('div', { class: 'tabs' });
    const panels = el('div');
    const defs = [
      ['quality', t('explore.quality')],
      ['profile', t('explore.profile')],
      ['preview', t('explore.preview')],
      ['correlations', t('explore.correlations')],
      ['sql', t('explore.sql')],
    ];
    defs.forEach(([key, label]) => {
      const b = el('button', { class: `tab ${key === tab ? 'active' : ''}`, text: label });
      b.onclick = async () => {
        tab = key;
        Array.from(tabs.children).forEach((c) => c.classList.toggle('active', c === b));
        await renderPanel(key);
      };
      tabs.appendChild(b);
    });
    host.appendChild(tabs);
    host.appendChild(panels);

    const self = this;
    async function renderPanel(key) {
      clear(panels);
      if (key === 'quality') panels.appendChild(qualityPanel(prof));
      else if (key === 'profile') {
        const grid = el('div', { class: 'grid grid-2' });
        prof.columns.forEach((c) => grid.appendChild(columnCard(c)));
        panels.appendChild(grid);
      } else if (key === 'preview') {
        const r = await api.get(`/api/datasets/${s.datasetId}/preview?limit=200`);
        panels.appendChild(el('div', { class: 'small muted mb-1',
          text: `${num(r.rows.length)} ${t('common.of')} ${num(r.total)} ${t('common.rows')}` }));
        panels.appendChild(table(r.columns.map((c) => ({ key: c, label: c })), r.rows,
          { compact: true, maxHeight: '560px' }));
      } else if (key === 'correlations') {
        panels.appendChild(el('div', { class: 'row' }, el('span', { class: 'spinner' })));
        const corr = await api.get(`/api/datasets/${s.datasetId}/correlations`);
        clear(panels).appendChild(correlationsPanel(corr));
      } else if (key === 'sql') {
        panels.appendChild(sqlPanel(s.datasetId));
      }
    }
    await renderPanel(tab);
  },
};
