/** Exportación: informe Excel corporativo y datos en CSV o Parquet. */
import * as api from '../api.js';
import { t, num, bytes, when } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import { el, clear, table, note, emptyState, fail, toast, jobPanel, icon } from '../ui.js';

let nav = null;

export default {
  mount(host, { go }) { nav = go; this.host = host; },
  async refresh() {
    const host = this.host;
    const s = store.get();
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('export.title') }),
      el('p', { class: 'page-lead', text: t('export.lead') })));

    if (!s.datasets.length && !s.models.length) {
      host.appendChild(emptyState(t('errors.no_dataset')));
      return;
    }

    /* ── informe Excel ─────────────────────────────────────────────────── */
    const dsSel = el('select', {},
      el('option', { value: '', text: `— ${t('common.none')} —` }),
      ...s.datasets.map((d) => el('option', {
        value: d.id, text: `${d.name} · ${num(d.rows)}`, selected: d.id === s.datasetId })));
    const mdSel = el('select', {},
      el('option', { value: '', text: `— ${t('common.none')} —` }),
      ...s.models.map((m) => el('option', { value: m.id, text: m.name, selected: m.id === s.modelId })));
    const chk = (labelKey, checked = true) => {
      const i = el('input', { type: 'checkbox', checked });
      return { input: i, node: el('label', { class: 'switch' }, i,
        el('span', { class: 'switch-track' }), el('span', { text: t(labelKey) })) };
    };
    const cProfile = chk('export.include_profile');
    const cEtl = chk('export.include_etl');
    const cData = chk('export.include_data');
    const limit = el('input', { type: 'number', value: '200000', min: '0', step: '10000' });

    const job = jobPanel(); job.root.classList.add('hidden');
    const out = el('div', { class: 'mt-2' });
    const btn = el('button', { class: 'btn btn-primary' }, icon('download', 15), t('export.generate'));

    const self = this;
    btn.onclick = async () => {
      if (!dsSel.value && !mdSel.value) { toast(t('errors.no_dataset'), 'warn'); return; }
      btn.disabled = true;
      job.root.classList.remove('hidden');
      job.reset();
      try {
        const r = await api.runJob('/api/exports/excel', {
          dataset_id: dsSel.value || null, model_id: mdSel.value || null,
          include_profile: cProfile.input.checked, include_etl: cEtl.input.checked,
          include_data: cData.input.checked, data_limit: Number(limit.value) || 0,
        }, (j) => job.update(j));
        audio.beep('done');
        clear(out).appendChild(note(
          `${r.filename} · ${bytes(r.size_bytes)} · ${r.sheets.join(' · ')}`, 'ok'));
        out.appendChild(el('a', { class: 'btn btn-primary mt-1', href: r.download_url, download: '' },
          icon('download', 15), t('common.download')));
        toast(r.filename, 'ok', t('common.success'));
        self.renderFiles();
      } catch (err) { fail(err); } finally { btn.disabled = false; }
    };

    host.appendChild(el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h2', { text: t('export.excel') })),
      el('div', { class: 'grid grid-2' },
        el('div', { class: 'field' }, el('label', { text: t('nav.data') }), dsSel),
        el('div', { class: 'field' }, el('label', { text: t('results.saved_models') }), mdSel)),
      el('div', { class: 'row mb-2' }, cProfile.node, cEtl.node, cData.node),
      el('div', { class: 'field' }, el('label', { text: t('export.data_limit') }), limit,
        el('div', { class: 'hint', text: t('export.excel_limit_note') })),
      el('div', { class: 'row' }, btn), job.root, out));

    /* ── datos crudos ──────────────────────────────────────────────────── */
    const dsSel2 = el('select', {}, ...s.datasets.map((d) => el('option', {
      value: d.id, text: `${d.name} · ${num(d.rows)}`, selected: d.id === s.datasetId })));
    const sep = el('select', {}, ...[[';', 'punto y coma ;'], [',', 'coma ,'], ['\t', 'tabulación']]
      .map(([v, l]) => el('option', { value: v, text: l })));
    const dec2 = el('select', {}, ...[[',', 'coma ,'], ['.', 'punto .']]
      .map(([v, l]) => el('option', { value: v, text: l })));
    const enc = el('select', {}, ...['utf-8-sig', 'utf-8', 'latin-1']
      .map((v) => el('option', { value: v, text: v })));
    const job2 = jobPanel(); job2.root.classList.add('hidden');
    const out2 = el('div', { class: 'mt-2' });

    const mkBtn = (fmt, label) => {
      const b = el('button', { class: 'btn' }, label);
      b.onclick = async () => {
        b.disabled = true;
        job2.root.classList.remove('hidden');
        job2.reset();
        try {
          const r = await api.runJob('/api/exports/data', {
            dataset_id: dsSel2.value, format: fmt, sep: sep.value,
            decimal: dec2.value, encoding: enc.value,
          }, (j) => job2.update(j));
          audio.beep('done');
          clear(out2).appendChild(note(`${r.filename} · ${num(r.rows)} ${t('common.rows')} · ${bytes(r.size_bytes)}`, 'ok'));
          out2.appendChild(el('a', { class: 'btn btn-primary mt-1', href: r.download_url, download: '' },
            icon('download', 15), t('common.download')));
          self.renderFiles();
        } catch (err) { fail(err); } finally { b.disabled = false; }
      };
      return b;
    };

    host.appendChild(el('div', { class: 'card' },
      el('div', { class: 'card-head' },
        el('div', {}, el('h2', { text: `${t('export.csv')} / ${t('export.parquet')}` }),
          el('div', { class: 'card-sub', text: t('export.csv_options') }))),
      el('div', { class: 'field' }, el('label', { text: t('nav.data') }), dsSel2),
      el('div', { class: 'grid grid-3' },
        el('div', { class: 'field' }, el('label', { text: t('export.separator') }), sep),
        el('div', { class: 'field' }, el('label', { text: t('export.decimal') }), dec2),
        el('div', { class: 'field' }, el('label', { text: t('export.encoding') }), enc)),
      el('div', { class: 'row' }, mkBtn('csv', 'CSV'), mkBtn('parquet', 'Parquet')),
      job2.root, out2));

    this.filesCard = el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h2', { text: t('export.files') })),
      el('div', { class: 'files-host' }));
    host.appendChild(this.filesCard);
    this.renderFiles();
  },

  async renderFiles() {
    const holder = this.filesCard?.querySelector('.files-host');
    if (!holder) return;
    try {
      const r = await api.get('/api/exports/list');
      clear(holder);
      if (!r.files.length) { holder.appendChild(emptyState(t('export.no_files'))); return; }
      holder.appendChild(table([
        { key: 'filename', label: t('common.name'), mono: true },
        { key: 'size_bytes', label: t('common.size'), align: 'right', format: (v) => bytes(v) },
        { key: 'modified', label: t('common.created'), format: (v) => when(v) },
        { key: 'download_url', label: '',
          render: (v) => el('a', { class: 'btn btn-sm', href: v, download: '' }, t('common.download')) },
      ], r.files, { maxHeight: '380px' }));
    } catch { /* la lista es accesoria */ }
  },
};
