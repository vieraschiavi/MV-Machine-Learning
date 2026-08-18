/** Vista de datos: subida de archivos, conexión SQL y datasets del workspace. */
import * as api from '../api.js';
import { t, num, bytes, when } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import { $, el, clear, icon, toast, fail, table, badge, confirmDialog, emptyState, jobPanel } from '../ui.js';

let nav = null;
let conn = { engine: 'postgresql' };

/* ── subida de archivos ──────────────────────────────────────────────────── */
function uploadCard() {
  const input = el('input', { type: 'file', class: 'hidden',
    accept: '.csv,.txt,.tsv,.dat,.psv,.xlsx,.xlsm,.xls,.xlsb,.ods,.parquet,.pq,.json,.jsonl,.ndjson' });
  const bar = el('div', { class: 'progress-bar' });
  const progress = el('div', { class: 'progress hidden', style: 'margin-top:14px' }, bar);
  const status = el('div', { class: 'small muted mt-1' });

  const zone = el('div', { class: 'dropzone' },
    el('div', { class: 'dropzone-title', text: t('data.upload_hint') }),
    el('div', { class: 'dropzone-sub', text: t('data.upload_formats') }));

  async function send(file) {
    if (!file) return;
    progress.classList.remove('hidden');
    bar.style.width = '2%';
    bar.className = 'progress-bar';
    status.textContent = `${t('data.uploading')} · ${file.name} · ${bytes(file.size)}`;
    try {
      const res = await api.uploadFile(file, {
        onProgress: (frac) => {
          bar.style.width = `${Math.max(frac * 90, 2)}%`;
          if (frac >= 1) status.textContent = t('data.processing');
        },
      });
      bar.style.width = '100%';
      bar.classList.add('done');
      status.textContent = `${res.dataset.name} · ${num(res.dataset.rows)} ${t('common.rows')} · ${res.dataset.n_columns} ${t('common.columns')}`;
      audio.beep('success');
      toast(`${res.dataset.name}: ${num(res.dataset.rows)} ${t('common.rows')}`, 'ok', t('common.success'));
      await store.refreshDatasets();
      store.set({ datasetId: res.dataset.id });
    } catch (err) {
      bar.classList.add('fail');
      status.textContent = '';
      fail(err.message === 'NETWORK' ? { message: 'NETWORK' } : err);
    }
  }

  zone.onclick = () => input.click();
  input.onchange = () => { send(input.files[0]); input.value = ''; };
  ['dragenter', 'dragover'].forEach((e) => zone.addEventListener(e, (ev) => {
    ev.preventDefault(); zone.classList.add('over');
  }));
  ['dragleave', 'drop'].forEach((e) => zone.addEventListener(e, (ev) => {
    ev.preventDefault(); zone.classList.remove('over');
  }));
  zone.addEventListener('drop', (ev) => send(ev.dataTransfer?.files?.[0]));

  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('data.upload_title') }),
        el('div', { class: 'card-sub', text: t('data.upload_nolimit') }))),
    zone, input, progress, status);
}

/* ── conexión SQL ────────────────────────────────────────────────────────── */
function sqlCard(rerender) {
  const engines = store.get().capabilities?.sql_engines || [];
  const engineSel = el('select', {},
    ...engines.map((e) => el('option', { value: e.id, text: e.label, selected: e.id === conn.engine })));
  const fields = el('div', { class: 'grid grid-3' });
  const result = el('div');
  const tablesBox = el('div', { class: 'mt-2' });
  const sqlBox = el('textarea', { class: 'mono', rows: '5', placeholder: 'SELECT * FROM esquema.tabla' });
  const nameInput = el('input', { type: 'text', placeholder: t('data.extract_name') });
  const job = jobPanel();
  job.root.classList.add('hidden');

  function renderFields() {
    clear(fields);
    const eng = engineSel.value;
    conn.engine = eng;
    const add = (key, labelKey, type = 'text', ph = '') => {
      const inp = el('input', { type, value: conn[key] ?? '', placeholder: ph });
      inp.oninput = () => { conn[key] = inp.value; };
      fields.appendChild(el('div', { class: 'field' }, el('label', { text: t(labelKey) }), inp));
    };
    add('label', 'data.connection_label', 'text', 'Producción');
    if (eng === 'custom') {
      add('url', 'data.connection_url', 'text', 'oracle+oracledb://usuario:clave@host:1521/?service_name=orcl');
    } else if (eng === 'sqlite' || eng === 'duckdb') {
      add('database', 'data.database', 'text', '/ruta/al/archivo.db');
    } else {
      add('host', 'data.host', 'text', '10.1.3.46');
      add('port', 'data.port', 'number');
      add('database', 'data.database');
      add('username', 'data.username');
      add('password', 'data.password', 'password');
    }
  }
  engineSel.onchange = renderFields;
  renderFields();

  const testBtn = el('button', { class: 'btn' }, t('data.test_connection'));
  const saveBtn = el('button', { class: 'btn' }, t('data.save_connection'));
  const browseBtn = el('button', { class: 'btn' }, t('data.browse_tables'));
  const previewBtn = el('button', { class: 'btn' }, t('common.preview'));
  const extractBtn = el('button', { class: 'btn btn-primary' }, t('data.extract'));

  const payload = () => ({ ...conn, port: conn.port ? Number(conn.port) : null });

  testBtn.onclick = async () => {
    testBtn.disabled = true;
    try {
      const r = await api.post('/api/connections/test', payload());
      clear(result).appendChild(el('div', { class: `note ${r.ok ? 'ok' : 'bad'}` },
        r.ok ? `${t('common.success')} · ${r.ms} ms · ${r.version || ''}` : r.error));
      audio.beep(r.ok ? 'success' : 'error');
    } catch (err) { fail(err); } finally { testBtn.disabled = false; }
  };

  saveBtn.onclick = async () => {
    try {
      const r = await api.post('/api/connections/save', payload());
      conn.id = r.connection.id;
      toast(t('common.success'), 'ok');
      rerender();
    } catch (err) { fail(err); }
  };

  browseBtn.onclick = async () => {
    if (!conn.id) { toast(t('data.save_connection'), 'warn'); return; }
    browseBtn.disabled = true;
    try {
      const r = await api.get(`/api/connections/${conn.id}/tables`);
      clear(tablesBox);
      if (r.schemas?.length > 1) {
        const sel = el('select', { style: 'max-width:240px' },
          ...r.schemas.map((s) => el('option', { value: s, text: s, selected: s === r.schema })));
        sel.onchange = async () => {
          const rr = await api.get(`/api/connections/${conn.id}/tables?schema=${encodeURIComponent(sel.value)}`);
          renderTables(rr);
        };
        tablesBox.appendChild(el('div', { class: 'field' }, el('label', { text: t('data.schema') }), sel));
      }
      renderTables(r);
    } catch (err) { fail(err); } finally { browseBtn.disabled = false; }

    function renderTables(r) {
      const list = el('div', { class: 'item-list', style: 'max-height:280px;overflow:auto' });
      (r.tables || []).forEach((tb) => {
        list.appendChild(el('div', {
          class: 'item',
          onClick: () => { sqlBox.value = `SELECT * FROM ${tb.schema ? `${tb.schema}.` : ''}${tb.name}`; },
        },
          icon('db', 15),
          el('div', { class: 'item-main' },
            el('div', { class: 'item-title', text: tb.name }),
            el('div', { class: 'item-meta', text: `${tb.type}${tb.schema ? ` · ${tb.schema}` : ''}` }))));
      });
      const prev = tablesBox.querySelector('.item-list');
      if (prev) prev.remove();
      tablesBox.appendChild(list.children.length ? list : emptyState(t('common.empty')));
    }
  };

  previewBtn.onclick = async () => {
    if (!conn.id) { toast(t('data.save_connection'), 'warn'); return; }
    previewBtn.disabled = true;
    try {
      const r = await api.post(`/api/connections/${conn.id}/preview`, { sql: sqlBox.value, limit: 50 });
      clear(result).appendChild(table(
        r.columns.map((c) => ({ key: c, label: c })), r.rows, { compact: true, maxHeight: '320px' }));
    } catch (err) { fail(err); } finally { previewBtn.disabled = false; }
  };

  extractBtn.onclick = async () => {
    if (!conn.id) { toast(t('data.save_connection'), 'warn'); return; }
    extractBtn.disabled = true;
    job.root.classList.remove('hidden');
    job.reset();
    try {
      const r = await api.runJob(`/api/connections/${conn.id}/extract`,
        { sql: sqlBox.value, name: nameInput.value || 'Extracción SQL' },
        (j) => job.update(j));
      toast(`${num(r.dataset.rows)} ${t('common.rows')}`, 'ok', t('common.success'));
      audio.beep('done');
      await store.refreshDatasets();
      store.set({ datasetId: r.dataset.id });
      rerender();
    } catch (err) { fail(err); } finally { extractBtn.disabled = false; }
  };

  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('data.sql_title') }),
        el('div', { class: 'card-sub', text: t('data.sql_hint') }))),
    el('div', { class: 'field' }, el('label', { text: t('data.engine') }), engineSel),
    fields,
    el('div', { class: 'row mb-2' }, testBtn, saveBtn, browseBtn),
    result,
    tablesBox,
    el('div', { class: 'field mt-2' },
      el('label', { text: t('data.query') }), sqlBox,
      el('div', { class: 'hint', text: `${t('data.query_hint')} ${t('data.read_only_note')}` })),
    el('div', { class: 'row' },
      el('div', { style: 'flex:1;min-width:220px' }, nameInput),
      previewBtn, extractBtn),
    job.root);
}

/* ── conexiones guardadas ────────────────────────────────────────────────── */
async function savedConnections(rerender) {
  let list = [];
  try { list = (await api.get('/api/connections')).connections; } catch { list = []; }
  if (!list.length) return null;
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h3', { text: t('data.saved_connections') })),
    el('div', { class: 'item-list' }, ...list.map((c) => el('div', {
      class: `item ${conn.id === c.id ? 'selected' : ''}`,
      onClick: () => { conn = { ...c, password: '' }; rerender(); },
    },
      icon('db', 15),
      el('div', { class: 'item-main' },
        el('div', { class: 'item-title', text: c.label || c.database || c.id }),
        el('div', { class: 'item-meta', text: `${c.engine} · ${c.host || c.database || c.url_masked || ''}` })),
      el('div', { class: 'item-actions' },
        el('button', {
          class: 'btn btn-sm btn-danger',
          onClick: async (e) => {
            e.stopPropagation();
            await api.del(`/api/connections/${c.id}`);
            rerender();
          },
        }, icon('trash', 14)))))));
}

/* ── datasets del workspace ──────────────────────────────────────────────── */
function datasetList() {
  const s = store.get();
  if (!s.datasets.length) return emptyState(t('common.empty'), t('data.lead'));
  return el('div', { class: 'item-list' }, ...s.datasets.map((d) => el('div', {
    class: `item ${d.id === s.datasetId ? 'selected' : ''}`,
    onClick: () => { store.set({ datasetId: d.id }); audio.beep('click'); toast(`${t('data.selected')}: ${d.name}`, 'ok'); },
  },
    icon(d.source === 'sql' ? 'db' : 'file', 16),
    el('div', { class: 'item-main' },
      el('div', { class: 'item-title', text: d.name }),
      el('div', { class: 'item-meta',
        text: `${num(d.rows)} ${t('common.rows')} · ${d.n_columns} ${t('common.columns')} · ${bytes(d.size_bytes)} · ${when(d.created_at)}` })),
    badge(t(`data.source_${d.source}`) || d.source, d.source === 'derived' ? 'accent' : ''),
    el('div', { class: 'item-actions' },
      el('button', {
        class: 'btn btn-sm', onClick: (e) => { e.stopPropagation(); store.set({ datasetId: d.id }); nav?.('explore'); },
      }, t('explore.title')),
      el('button', {
        class: 'btn btn-sm btn-danger',
        onClick: (e) => {
          e.stopPropagation();
          confirmDialog(t('data.delete_confirm'), async () => {
            await api.del(`/api/datasets/${d.id}`);
            await store.refreshDatasets();
          });
        },
      }, icon('trash', 14))))));
}

export default {
  mount(host, { go }) {
    nav = go;
    this.host = host;
    this.render();
    store.subscribe((_, keys) => { if (keys.includes('datasets') || keys.includes('datasetId')) this.renderList(); });
  },
  refresh() { this.render(); },
  async render() {
    const host = this.host;
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('data.title') }),
      el('p', { class: 'page-lead', text: t('data.lead') })));
    host.appendChild(uploadCard());
    host.appendChild(sqlCard(() => this.render()));
    const saved = await savedConnections(() => this.render());
    if (saved) host.appendChild(saved);
    this.listCard = el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h2', { text: t('data.datasets_title') })),
      el('div', { class: 'list-host' }, datasetList()));
    host.appendChild(this.listCard);
  },
  renderList() {
    const holder = this.listCard?.querySelector('.list-host');
    if (holder) clear(holder).appendChild(datasetList());
  },
};
