/** Vista de ETL: proponer el plan, revisarlo, auditar fuga y ejecutarlo. */
import * as api from '../api.js';
import { t, num, dec } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import { el, clear, table, badge, note, emptyState, fail, toast, jobPanel, icon } from '../ui.js';

let nav = null;

const OPT_KEYS = [
  ['drop_constant', 'etl.opt_drop_constant', 'bool'],
  ['drop_identifiers', 'etl.opt_drop_identifiers', 'bool'],
  ['impute', 'etl.opt_impute', 'bool'],
  ['missing_indicator', 'etl.opt_missing_indicator', 'bool'],
  ['parse_dates', 'etl.opt_parse_dates', 'bool'],
  ['cast_numeric_text', 'etl.opt_cast_numeric', 'bool'],
  ['group_rare', 'etl.opt_group_rare', 'bool'],
  ['clip_outliers', 'etl.opt_clip_outliers', 'bool'],
  ['drop_duplicates', 'etl.opt_drop_duplicates', 'bool'],
  ['leakage_audit', 'etl.opt_leakage', 'bool'],
  ['null_threshold', 'etl.opt_null_threshold', 'number'],
];

function optionsCard(options, onChange) {
  const grid = el('div', { class: 'grid grid-3' });
  OPT_KEYS.forEach(([key, labelKey, type]) => {
    if (type === 'bool') {
      const inp = el('input', { type: 'checkbox', checked: options[key] !== false });
      inp.onchange = () => onChange(key, inp.checked);
      grid.appendChild(el('label', { class: 'switch' }, inp,
        el('span', { class: 'switch-track' }), el('span', { text: t(labelKey) })));
    } else {
      const inp = el('input', { type: 'number', min: '10', max: '100', step: '5', value: options[key] ?? 80 });
      inp.onchange = () => onChange(key, Number(inp.value));
      grid.appendChild(el('div', { class: 'field mb-0' }, el('label', { text: t(labelKey) }), inp));
    }
  });
  return el('details', { class: 'card' },
    el('summary', { style: 'cursor:pointer;font-weight:600', text: t('etl.options') }),
    el('div', { class: 'mt-2' }, grid));
}

function stepsCard(plan, rerender) {
  const list = el('div');
  plan.steps.forEach((s) => {
    const chk = el('input', { type: 'checkbox', checked: s.enabled !== false });
    chk.onchange = () => { s.enabled = chk.checked; rerender(); };
    list.appendChild(el('div', { class: 'step-row' },
      el('label', { class: 'switch' }, chk, el('span', { class: 'switch-track' })),
      el('div', {},
        el('div', { class: 'step-op', text: s.op }),
        s.column ? el('div', { class: 'step-col mono', text: s.column }) : null),
      el('div', { class: 'step-reason', text: s.reason })));
  });
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('etl.steps') }),
        el('div', { class: 'card-sub',
          text: `${plan.steps.filter((s) => s.enabled !== false).length} / ${plan.steps.length}` }))),
    plan.steps.length ? list : emptyState(t('common.empty')));
}

function leakageCard(findings) {
  if (!findings?.length) return el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h2', { text: t('etl.leakage_title') })),
    note(t('etl.leakage_none'), 'ok'));
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('etl.leakage_title') }),
        el('div', { class: 'card-sub', text: t('etl.leakage_note') }))),
    table([
      { key: 'column', label: t('common.column'), mono: true },
      { key: 'blocked', label: t('common.status'),
        render: (v) => badge(v ? t('etl.blocked') : t('etl.review'), v ? 'bad' : 'warn') },
      { key: 'metric', label: 'Métrica' },
      { key: 'value', label: t('common.value'), align: 'right', format: (v) => dec(v, 4) },
      { key: 'detail', label: t('common.detail') },
    ], findings));
}

export default {
  mount(host, { go }) { nav = go; this.host = host; },
  async refresh() {
    const host = this.host;
    const s = store.get();
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('etl.title') }),
      el('p', { class: 'page-lead', text: t('etl.lead') })));

    if (!s.datasetId) {
      host.appendChild(emptyState(t('errors.no_dataset')));
      host.appendChild(el('button', { class: 'btn btn-primary mt-2', onClick: () => nav('data') }, t('nav.data')));
      return;
    }

    const cols = store.columns();
    const targetSel = el('select', { style: 'max-width:320px' },
      el('option', { value: '', text: `— ${t('common.none')} —` }),
      ...cols.map((c) => el('option', { value: c, text: c, selected: c === s.target })));
    targetSel.onchange = () => store.set({ target: targetSel.value || null });

    let options = { ...(s.etlPlan?.options || {}) };
    const proposeBtn = el('button', { class: 'btn btn-primary' }, t('etl.propose'));
    const body = el('div');
    const optHost = el('div');

    const renderOptions = () => {
      clear(optHost).appendChild(optionsCard(options, (k, v) => { options[k] = v; }));
    };
    renderOptions();

    host.appendChild(el('div', { class: 'card' },
      el('div', { class: 'row' },
        el('div', { class: 'field mb-0', style: 'flex:1;min-width:260px' },
          el('label', { text: t('etl.target_for_etl') }), targetSel),
        proposeBtn)));
    host.appendChild(optHost);
    host.appendChild(body);

    const self = this;
    proposeBtn.onclick = async () => {
      proposeBtn.disabled = true;
      clear(body).appendChild(el('div', { class: 'card' },
        el('div', { class: 'row' }, el('span', { class: 'spinner' }), el('span', { text: t('common.loading') }))));
      try {
        const plan = await api.post('/api/etl/propose', {
          dataset_id: s.datasetId, target: targetSel.value || null, options,
        });
        store.set({ etlPlan: plan });
        options = { ...plan.options };
        renderOptions();
        renderPlan(plan);
        audio.beep('success');
      } catch (err) { clear(body); fail(err); } finally { proposeBtn.disabled = false; }
    };

    function renderPlan(plan) {
      clear(body);
      body.appendChild(el('div', { class: 'grid grid-4 mb-2' },
        el('div', { class: 'stat' },
          el('div', { class: 'stat-label', text: t('etl.steps') }),
          el('div', { class: 'stat-value', text: num(plan.summary.n_steps) })),
        el('div', { class: 'stat' },
          el('div', { class: 'stat-label', text: t('common.columns') }),
          el('div', { class: 'stat-value', text: num(plan.summary.columns_in) }),
          el('div', { class: 'stat-sub', text: `${plan.summary.columns_dropped} descartadas` })),
        el('div', { class: 'stat' },
          el('div', { class: 'stat-label', text: t('common.rows') }),
          el('div', { class: 'stat-value', text: num(plan.summary.rows_in) })),
        el('div', { class: `stat ${plan.leakage?.some((l) => l.blocked) ? 'bad' : 'ok'}` },
          el('div', { class: 'stat-label', text: t('etl.leakage_title') }),
          el('div', { class: 'stat-value', text: num(plan.leakage?.length || 0) }))));

      const sqlBox = el('pre', { class: 'code', text: plan.sql });
      const stepsHost = el('div');
      const rerenderSql = async () => {
        try {
          const r = await api.post('/api/etl/compile', { dataset_id: plan.dataset_id, plan });
          plan.sql = r.sql;
          sqlBox.textContent = r.sql;
        } catch (err) { fail(err); }
      };
      const renderSteps = () => { clear(stepsHost).appendChild(stepsCard(plan, rerenderSql)); };
      renderSteps();

      body.appendChild(stepsHost);
      body.appendChild(leakageCard(plan.leakage));
      body.appendChild(el('div', { class: 'card' },
        el('div', { class: 'card-head' },
          el('div', {}, el('h2', { text: t('etl.sql_generated') }),
            el('div', { class: 'card-sub', text: t('etl.sql_note') }))),
        sqlBox));

      const job = jobPanel();
      job.root.classList.add('hidden');
      const runBtn = el('button', { class: 'btn btn-primary' }, t('etl.execute'));
      const aiBtn = el('button', { class: 'btn' }, t('etl.ai_review'));
      const result = el('div', { class: 'mt-2' });

      runBtn.onclick = async () => {
        runBtn.disabled = true;
        job.root.classList.remove('hidden');
        job.reset();
        try {
          const r = await api.runJob('/api/etl/execute',
            { dataset_id: plan.dataset_id, plan }, (j) => job.update(j));
          store.set({ etlResult: r });
          await store.refreshDatasets();
          store.set({ datasetId: r.dataset.id, profile: null });
          audio.beep('done');
          audio.speak(`${t('etl.result_title')}. ${num(r.rows_out)} ${t('common.rows')}, ${r.columns_out} ${t('common.columns')}.`);
          clear(result).appendChild(el('div', { class: 'card' },
            el('div', { class: 'card-head' }, el('h2', { text: t('etl.result_title') })),
            el('div', { class: 'grid grid-4' },
              el('div', { class: 'stat' }, el('div', { class: 'stat-label', text: t('etl.rows_in') }),
                el('div', { class: 'stat-value', text: num(r.rows_in) })),
              el('div', { class: 'stat ok' }, el('div', { class: 'stat-label', text: t('etl.rows_out') }),
                el('div', { class: 'stat-value', text: num(r.rows_out) })),
              el('div', { class: 'stat' }, el('div', { class: 'stat-label', text: t('etl.rows_removed') }),
                el('div', { class: 'stat-value', text: num(r.rows_removed) })),
              el('div', { class: 'stat' }, el('div', { class: 'stat-label', text: t('etl.columns_out') }),
                el('div', { class: 'stat-value', text: num(r.columns_out) }))),
            el('div', { class: 'row mt-2' },
              el('button', { class: 'btn btn-primary', onClick: () => nav('model') }, t('nav.model')),
              el('button', { class: 'btn', onClick: () => nav('explore') }, t('nav.explore')))));
          toast(`${num(r.rows_out)} ${t('common.rows')} · ${r.columns_out} ${t('common.columns')}`, 'ok', t('common.success'));
        } catch (err) { fail(err); } finally { runBtn.disabled = false; }
      };

      aiBtn.onclick = async () => {
        aiBtn.disabled = true;
        try {
          const r = await api.post('/api/ai/review-etl', { plan });
          const items = [];
          if (r.veredicto) items.push(note(r.veredicto, 'accent'));
          ['riesgos', 'faltantes'].forEach((k) => {
            if (r[k]?.length) {
              items.push(el('h4', { class: 'mt-2', text: k }));
              items.push(el('ul', {}, ...r[k].map((x) => el('li', { text: String(x) }))));
            }
          });
          clear(result).appendChild(el('div', { class: 'card' },
            el('div', { class: 'card-head' }, el('h2', { text: t('etl.ai_review') })), ...items));
        } catch (err) { fail(err); } finally { aiBtn.disabled = false; }
      };

      body.appendChild(el('div', { class: 'card' },
        el('div', { class: 'row' }, runBtn, aiBtn), job.root));
      body.appendChild(result);
    }

    if (s.etlPlan && s.etlPlan.dataset_id === s.datasetId) renderPlan(s.etlPlan);
  },
};
