/** Vista de datos: subida de archivos, conexión SQL y datasets del workspace. */
import * as api from '../api.js';
import { t, num, bytes, when } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import { $, el, clear, icon, toast, fail, table, badge, confirmDialog, emptyState, jobPanel } from '../ui.js';

let nav = null;
let conn = { engine: 'postgresql' };
// Analysis Services: el modelo elegido en «Explorar tablas» (los modelos del servidor se listan como esquemas).
let esquema = null;

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
      // Un Excel de varias hojas deja un dataset por hoja; queda activa la más útil.
      if ((res.hojas || []).length > 1) {
        status.textContent += ` · ${t('data.hojas_cargadas')}: ${res.hojas.map((h) => h.sheet || h.name).join(', ')}`;
      }
      audio.beep('success');
      toast(`${res.dataset.name}: ${num(res.dataset.rows)} ${t('common.rows')}`, 'ok', t('common.success'));
      await store.refreshDatasets();
      await store.elegirDataset(res.dataset.id);
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
  const engineHint = el('div', { class: 'hint mb-2' });
  const result = el('div');
  const tablesBox = el('div', { class: 'mt-2' });
  const sqlBox = el('textarea', { class: 'mono', rows: '5', placeholder: 'SELECT * FROM esquema.tabla' });
  const queryLabel = el('label', { text: t('data.query') });
  const queryHint = el('div', { class: 'hint', text: `${t('data.query_hint')} ${t('data.read_only_note')}` });
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
    // Los ejemplos también son texto de la interfaz: escritos a mano quedaban
    // en castellano dentro de la aplicación en inglés, y el del host era el
    // servidor real de casa — que además salía filmado en los videos de la web.
    add('label', 'data.connection_label', 'text', t('data.ph_label'));
    if (eng === 'custom') {
      add('url', 'data.connection_url', 'text', t('data.ph_url'));
    } else if (eng === 'fabric') {
      // Fabric no tiene usuario y contraseña de base: la identidad la da Entra ID.
      // El puerto es siempre 1433 y no se muestra: si quedó uno de otro motor
      // en el formulario, la conexión se iba a ese puerto y no contra Fabric.
      conn.port = null;
      add('host', 'data.fabric_endpoint', 'text', t('data.ph_fabric_endpoint'));
      add('database', 'data.fabric_database', 'text', t('data.ph_fabric_database'));
      add('username', 'data.fabric_identity', 'text', t('data.ph_fabric_identity'));
      add('password', 'data.fabric_secret', 'password', t('data.ph_fabric_secret'));
    } else if (eng === 'aas') {
      // Analysis Services (el MDW) habla DAX, no SQL: servidor asazure://, modelo y cómo entrar.
      conn.port = null;
      conn.auth = conn.auth || 'usuario';
      add('host', 'data.aas_server', 'text', t('data.ph_aas_server'));
      add('database', 'data.aas_model', 'text', t('data.ph_aas_model'));
      const authSel = el('select', {},
        ...['usuario', 'ventana', 'token'].map((a) => el('option',
          { value: a, text: t(`data.aas_auth_${a}`), selected: a === conn.auth })));
      authSel.onchange = () => { conn.auth = authSel.value; renderFields(); };
      fields.appendChild(el('div', { class: 'field' }, el('label', { text: t('data.aas_auth') }), authSel));
      if (conn.auth === 'usuario') {
        add('username', 'data.username', 'text', t('data.ph_aas_user'));
        add('password', 'data.password', 'password');
      } else if (conn.auth === 'token') {
        add('password', 'data.aas_token', 'password');
      }
    } else if (eng === 'sqlite' || eng === 'duckdb') {
      add('database', 'data.database', 'text', t('data.ph_file'));
    } else {
      add('host', 'data.host', 'text', t('data.ph_host'));
      add('port', 'data.port', 'number');
      add('database', 'data.database');
      add('username', 'data.username');
      add('password', 'data.password', 'password');
    }
  }
  function renderAll() {
    renderFields();
    const eng = engineSel.value;
    engineHint.textContent = eng === 'fabric' ? t('data.fabric_hint') : eng === 'aas' ? t('data.aas_hint') : '';
    sqlBox.placeholder = eng === 'aas' ? t('data.aas_query_ph') : 'SELECT * FROM esquema.tabla';
    queryLabel.textContent = t(eng === 'aas' ? 'data.aas_query' : 'data.query');
    queryHint.textContent = eng === 'aas' ? t('data.aas_query_hint')
      : `${t('data.query_hint')} ${t('data.read_only_note')}`;
    if (eng !== 'aas') esquema = null;
  }
  engineSel.onchange = renderAll;
  renderAll();

  const testBtn = el('button', { class: 'btn' }, t('data.test_connection'));
  const saveBtn = el('button', { class: 'btn' }, t('data.save_connection'));
  const browseBtn = el('button', { class: 'btn' }, t('data.browse_tables'));
  const previewBtn = el('button', { class: 'btn' }, t('common.preview'));
  const extractBtn = el('button', { class: 'btn btn-primary' }, t('data.extract'));
  const esAAS = () => conn.engine === 'aas';

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
          try {
            const rr = await api.get(`/api/connections/${conn.id}/tables?schema=${encodeURIComponent(sel.value)}`);
            esquema = rr.schema;
            renderTables(rr);
          } catch (err) { fail(err); }
        };
        if (esAAS() && !r.schema) sel.prepend(el('option', { value: '', text: '—', selected: true }));
        tablesBox.appendChild(el('div', { class: 'field' },
          el('label', { text: t(esAAS() ? 'data.aas_model' : 'data.schema') }), sel));
      }
      esquema = esAAS() ? r.schema : null;
      renderTables(r);
    } catch (err) { fail(err); } finally { browseBtn.disabled = false; }

    function renderTables(r) {
      const list = el('div', { class: 'item-list', style: 'max-height:280px;overflow:auto' });
      const elegidas = new Map();
      const multiBtn = el('button', { class: 'btn btn-primary', disabled: true }, t('data.extract_selected'));
      const contar = () => {
        multiBtn.disabled = !elegidas.size;
        multiBtn.textContent = `${t('data.extract_selected')}${elegidas.size ? ` (${elegidas.size})` : ''}`;
      };
      (r.tables || []).forEach((tb) => {
        // Una casilla por tabla: varias tablas del mismo servidor o del mismo modelo, un dataset por tabla.
        const marca = el('input', { type: 'checkbox', 'aria-label': tb.name });
        marca.onclick = (e) => e.stopPropagation();
        marca.onchange = () => {
          if (marca.checked) elegidas.set(`${tb.schema || ''}.${tb.name}`, tb);
          else elegidas.delete(`${tb.schema || ''}.${tb.name}`);
          contar();
        };
        list.appendChild(el('div', {
          class: 'item',
          onClick: () => {
            sqlBox.value = esAAS()
              ? `EVALUATE '${String(tb.name).replace(/'/g, "''")}'`
              : `SELECT * FROM ${tb.schema ? `${tb.schema}.` : ''}${tb.name}`;
            if (!nameInput.value) nameInput.value = tb.name;
          },
        },
          marca,
          icon('db', 15),
          el('div', { class: 'item-main' },
            el('div', { class: 'item-title', text: tb.name }),
            el('div', { class: 'item-meta', text: `${tb.type}${tb.schema ? ` · ${tb.schema}` : ''}` }))));
      });
      multiBtn.onclick = async () => {
        multiBtn.disabled = true;
        job.root.classList.remove('hidden');
        job.reset();
        try {
          const tablas = [...elegidas.values()].map((tb) => ({ name: tb.name, schema_: tb.schema || null }));
          const rr = await api.runJob(`/api/connections/${conn.id}/extract-many`, { tables: tablas },
            (j) => job.update(j));
          const filas = rr.datasets.reduce((a, d) => a + (d.rows || 0), 0);
          toast(`${rr.datasets.length} dataset(s) · ${num(filas)} ${t('common.rows')}`, 'ok', t('common.success'));
          (rr.errors || []).forEach((e) => toast(`${e.table}: ${e.error}`, 'warn'));
          audio.beep('done');
          await store.refreshDatasets();
          await store.elegirDataset(rr.datasets[0].id);
          rerender();
        } catch (err) { fail(err); } finally { contar(); }
      };
      tablesBox.querySelectorAll('.item-list, .empty-state, .multi-row').forEach((n) => n.remove());
      const vacio = esAAS() && !r.schema ? t('data.aas_pick_model') : t('common.empty');
      tablesBox.appendChild(list.children.length ? list : emptyState(vacio));
      if (list.children.length) {
        tablesBox.appendChild(el('div', { class: 'row mt-1 multi-row' },
          el('div', { class: 'hint', style: 'flex:1', text: t('data.extract_selected_hint') }), multiBtn));
      }
    }
  };

  previewBtn.onclick = async () => {
    if (!conn.id) { toast(t('data.save_connection'), 'warn'); return; }
    previewBtn.disabled = true;
    try {
      const r = await api.post(`/api/connections/${conn.id}/preview`,
        { sql: sqlBox.value, limit: 50, esquema });
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
        { sql: sqlBox.value, name: nameInput.value || 'Extracción SQL', esquema },
        (j) => job.update(j));
      toast(`${num(r.dataset.rows)} ${t('common.rows')}`, 'ok', t('common.success'));
      audio.beep('done');
      await store.refreshDatasets();
      await store.elegirDataset(r.dataset.id);
      rerender();
    } catch (err) { fail(err); } finally { extractBtn.disabled = false; }
  };

  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('data.sql_title') }),
        el('div', { class: 'card-sub', text: t('data.sql_hint') }))),
    el('div', { class: 'field' }, el('label', { text: t('data.engine') }), engineSel),
    fields,
    engineHint,
    el('div', { class: 'row mb-2' }, testBtn, saveBtn, browseBtn),
    result,
    tablesBox,
    el('div', { class: 'field mt-2' },
      queryLabel, sqlBox, queryHint),
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
    onClick: () => { store.elegirDataset(d.id); audio.beep('click'); toast(`${t('data.selected')}: ${d.name}`, 'ok'); },
  },
    icon(d.source === 'sql' || d.source === 'aas' ? 'db' : 'file', 16),
    el('div', { class: 'item-main' },
      el('div', { class: 'item-title', text: d.name }),
      el('div', { class: 'item-meta',
        text: `${num(d.rows)} ${t('common.rows')} · ${d.n_columns} ${t('common.columns')} · ${bytes(d.size_bytes)} · ${when(d.created_at)}` })),
    badge(t(`data.source_${d.source}`) || d.source, d.source === 'derived' ? 'accent' : ''),
    el('div', { class: 'item-actions' },
      el('button', {
        class: 'btn btn-sm', onClick: (e) => { e.stopPropagation(); store.elegirDataset(d.id); nav?.('explore'); },
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
    // Dos renders que se solapan se pisan: los dos limpian, los dos esperan a
    // las conexiones guardadas y los dos agregan su lista, así que «Datasets
    // del workspace» aparecía dos veces. Gana el último que arrancó.
    const mio = (this.generacion = (this.generacion || 0) + 1);
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('data.title') }),
      el('p', { class: 'page-lead', text: t('data.lead') })));
    host.appendChild(uploadCard());
    host.appendChild(sqlCard(() => this.render()));
    const saved = await savedConnections(() => this.render());
    if (mio !== this.generacion) return;
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
