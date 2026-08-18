/** Modelado: definir el objetivo en lenguaje natural, configurar y entrenar. */
import * as api from '../api.js';
import * as charts from '../charts.js';
import { t, num, pct, dec } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import { el, clear, table, badge, note, emptyState, fail, toast, jobPanel, icon } from '../ui.js';

let nav = null;
let cfg = {
  budget_seconds: 120, max_models: 6, feature_selection: true, calibrate: true,
  ensemble: true, shap: true, permutation_importance: true, time_column: null,
  metric: null, exclude: [], models: null,
};
let familyCatalog = null;

async function loadCatalog() {
  if (familyCatalog) return familyCatalog;
  try { familyCatalog = (await api.get('/api/automl/catalog')).families; }
  catch { familyCatalog = []; }
  return familyCatalog;
}

/* ── el cartel: escribí qué querés predecir ──────────────────────────────── */
function objectiveCard(onTarget) {
  const s = store.get();
  const cols = store.columns();
  const input = el('textarea', {
    rows: '2', placeholder: t('model.objective_placeholder'),
    style: 'font-size:15px;padding:12px 14px',
  });
  input.value = localStorage.getItem('mv.objective') || '';

  const targetSel = el('select', { style: 'max-width:340px' },
    el('option', { value: '', text: `— ${t('common.select')} —` }),
    ...cols.map((c) => el('option', { value: c, text: c, selected: c === s.target })));
  targetSel.onchange = () => { store.set({ target: targetSel.value || null }); onTarget(); };

  const result = el('div', { class: 'mt-1' });
  const idBtn = el('button', { class: 'btn btn-primary' }, t('model.identify'));
  const micBtn = el('button', { class: 'btn btn-icon', 'data-i18n-title': 'topbar.voice_input' }, icon('mic'));

  micBtn.onclick = () => {
    if (!audio.dictationSupported()) { toast(t('audio.voice_unsupported'), 'warn'); return; }
    micBtn.classList.add('btn-primary');
    audio.dictate({
      onResult: (text) => { input.value = text; },
      onEnd: () => micBtn.classList.remove('btn-primary'),
      onError: (e) => { micBtn.classList.remove('btn-primary'); toast(String(e), 'warn'); },
    });
  };

  idBtn.onclick = async () => {
    const objective = input.value.trim();
    if (!objective) { toast(t('model.objective_hint'), 'warn'); return; }
    localStorage.setItem('mv.objective', objective);
    idBtn.disabled = true;
    clear(result).appendChild(el('div', { class: 'row' }, el('span', { class: 'spinner' })));
    try {
      const r = await api.post('/api/ai/suggest-target', { dataset_id: s.datasetId, objective });
      clear(result);
      if (r.target) {
        targetSel.value = r.target;
        store.set({ target: r.target, task: r.task || null });
        result.appendChild(el('div', { class: 'note accent' },
          el('div', { class: 'row row-tight mb-1' },
            badge(`${t('model.target_column')}: ${r.target}`, 'accent'),
            r.task ? badge(t(`model.task_${r.task}`)) : null,
            r.confidence != null ? badge(`${t('model.confidence')} ${pct(r.confidence, 0)}`) : null,
            badge(r.source || 'IA')),
          el('div', { class: 'small', text: r.reason || '' })));
        if (r.exclude?.length) {
          cfg.exclude = r.exclude.filter((c) => cols.includes(c));
          if (cfg.exclude.length) {
            result.appendChild(note(`${t('model.exclude_columns')}: ${cfg.exclude.join(', ')}`, 'warn'));
          }
        }
        audio.beep('success');
        onTarget();
      } else {
        result.appendChild(note(r.reason || r.warning || t('errors.no_target'), 'warn'));
        if (r.alternatives?.length) {
          result.appendChild(el('div', { class: 'row row-tight mt-1' },
            ...r.alternatives.map((c) => el('button', {
              class: 'btn btn-sm',
              onClick: () => { targetSel.value = c; store.set({ target: c }); onTarget(); },
            }, c))));
        }
      }
      if (r.ai_error) result.appendChild(note(r.ai_error, 'warn'));
    } catch (err) { clear(result); fail(err); } finally { idBtn.disabled = false; }
  };

  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('model.objective_label') }),
        el('div', { class: 'card-sub', text: t('model.objective_hint') }))),
    el('div', { class: 'row', style: 'align-items:flex-start' },
      el('div', { style: 'flex:1;min-width:280px' }, input),
      micBtn, idBtn),
    result,
    el('div', { class: 'field mt-2 mb-0' },
      el('label', { text: t('model.target_column') }), targetSel));
}

/* ── análisis del objetivo ───────────────────────────────────────────────── */
async function targetAnalysis(datasetId, target) {
  const box = el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h2', { text: t('model.target_analysis') })),
    el('div', { class: 'row' }, el('span', { class: 'spinner' })));
  try {
    const r = await api.get(`/api/datasets/${datasetId}/target-analysis?target=${encodeURIComponent(target)}`);
    clear(box);
    box.appendChild(el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('model.target_analysis') }),
        el('div', { class: 'card-sub', text: `${target} · ${t(`model.task_${r.task}`)}` }))));
    const d = r.distribution;
    if (d.type === 'categorical') {
      box.appendChild(el('div', { class: 'grid grid-2' },
        charts.hbars(d.classes.map((c) => ({ label: c.value, value: c.count })),
          { title: t('model.class_balance'), width: 460, fmt: (v) => num(v), maxItems: 12 }),
        el('div', {},
          el('dl', { class: 'kv' },
            el('dt', { text: t('model.detected_task') }), el('dd', { text: t(`model.task_${r.task}`) }),
            el('dt', { text: 'Clases' }), el('dd', { text: num(d.n_classes) }),
            el('dt', { text: t('model.imbalance') }), el('dd', { text: `${dec(d.imbalance_ratio, 2)} : 1` }),
            el('dt', { text: 'Clase minoritaria' }), el('dd', { text: pct(d.minority_pct, 2, true) })),
          d.imbalance_ratio > 20
            ? note('Desbalance fuerte: la exactitud simple deja de ser informativa. Se prioriza PR-AUC y recall.', 'warn')
            : null)));
    } else {
      box.appendChild(el('dl', { class: 'kv' },
        el('dt', { text: t('explore.mean') }), el('dd', { text: dec(d.mean, 2) }),
        el('dt', { text: t('explore.median') }), el('dd', { text: dec(d.median, 2) }),
        el('dt', { text: t('explore.std') }), el('dd', { text: dec(d.std, 2) }),
        el('dt', { text: `${t('explore.min')} / ${t('explore.max')}` }),
        el('dd', { text: `${dec(d.min, 2)} / ${dec(d.max, 2)}` }),
        el('dt', { text: 'Asimetría' }), el('dd', { text: dec(d.skew, 3) })));
      if (Math.abs(d.skew || 0) > 1.5) {
        box.appendChild(note('Objetivo sesgado: se modela en logaritmo y se corrige el sesgo de escala con el factor de smearing de Duan, para que el total predicho cierre contra el real.', 'accent'));
      }
    }
    box.appendChild(el('h3', { class: 'mt-3 mb-1', text: t('model.associations') }));
    box.appendChild(charts.hbars(
      r.associations.slice(0, 14).map((a) => ({ label: a.column, value: a.strength })),
      { width: 620, fmt: (v) => dec(v, 3) }));
    box.appendChild(table([
      { key: 'column', label: t('common.column'), mono: true },
      { key: 'metric', label: 'Métrica' },
      { key: 'value', label: t('common.value'), align: 'right', format: (v) => dec(v, 4) },
      { key: 'strength', label: 'Fuerza', align: 'right', format: (v) => dec(v, 4) },
    ], r.associations, { maxHeight: '300px', compact: true }));
  } catch (err) { clear(box).appendChild(note(err.message, 'bad')); }
  return box;
}

/* ── catálogo de familias ────────────────────────────────────────────────── */
function familiesBlock() {
  const host = el('div', { class: 'field' },
    el('label', { text: t('model.families') }),
    el('div', { class: 'small muted', text: t('common.loading') }));
  loadCatalog().then((families) => {
    const grid = el('div', { style: 'display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:8px' });
    families.forEach((f) => {
      const inp = el('input', { type: 'checkbox', checked: (cfg.models || []).includes(f.name),
        disabled: !f.available });
      inp.onchange = () => {
        const set = new Set(cfg.models || []);
        if (inp.checked) set.add(f.name); else set.delete(f.name);
        cfg.models = set.size ? [...set] : null;
        hint.textContent = cfg.models
          ? `${cfg.models.length} ${t('model.families').toLowerCase()}`
          : t('model.families_auto');
      };
      grid.appendChild(el('label', { class: 'switch', title: f.description },
        inp, el('span', { class: 'switch-track' }),
        el('span', { text: f.label })));
    });
    const hint = el('div', { class: 'hint',
      text: cfg.models ? `${cfg.models.length}` : t('model.families_auto') });
    clear(host);
    host.appendChild(el('label', { text: t('model.families') }));
    host.appendChild(grid);
    host.appendChild(hint);
    host.appendChild(el('div', { class: 'hint', text: t('model.families_hint') }));
  });
  return host;
}

/* ── configuración ───────────────────────────────────────────────────────── */
function configCard() {
  const cols = store.columns();
  const s = store.get();
  const timeSel = el('select', {},
    el('option', { value: '', text: `— ${t('common.none')} —` }),
    ...cols.map((c) => el('option', { value: c, text: c, selected: c === cfg.time_column })));
  timeSel.onchange = () => { cfg.time_column = timeSel.value || null; };

  const budget = el('input', { type: 'range', min: '20', max: '900', step: '10', value: cfg.budget_seconds });
  const budgetLbl = el('label', { text: `${t('model.budget')}: ${cfg.budget_seconds}s` });
  budget.oninput = () => {
    cfg.budget_seconds = Number(budget.value);
    budgetLbl.textContent = `${t('model.budget')}: ${cfg.budget_seconds}s`;
  };

  const models = el('input', { type: 'range', min: '1', max: '7', step: '1', value: cfg.max_models });
  const modelsLbl = el('label', { text: `${t('model.max_models')}: ${cfg.max_models}` });
  models.oninput = () => {
    cfg.max_models = Number(models.value);
    modelsLbl.textContent = `${t('model.max_models')}: ${cfg.max_models}`;
  };

  const metricSel = el('select', {},
    el('option', { value: '', text: t('model.metric_auto') }),
    ...['auc', 'pr_auc', 'ks', 'f1', 'f1_macro', 'balanced_accuracy', 'accuracy',
      'r2', 'wmape', 'rmse', 'mae'].map((m) => el('option', { value: m, text: m, selected: m === cfg.metric })));
  metricSel.onchange = () => { cfg.metric = metricSel.value || null; };

  const excludeSel = el('select', { multiple: true, size: '6' },
    ...cols.filter((c) => c !== s.target).map((c) => el('option', {
      value: c, text: c, selected: cfg.exclude.includes(c),
    })));
  excludeSel.onchange = () => {
    cfg.exclude = Array.from(excludeSel.selectedOptions).map((o) => o.value);
  };

  const toggles = [
    ['feature_selection', 'model.feature_selection'],
    ['calibrate', 'model.calibrate'],
    ['ensemble', 'model.ensemble'],
    ['shap', 'model.shap'],
  ].map(([key, labelKey]) => {
    const inp = el('input', { type: 'checkbox', checked: cfg[key] });
    inp.onchange = () => { cfg[key] = inp.checked; };
    return el('label', { class: 'switch' }, inp, el('span', { class: 'switch-track' }),
      el('span', { text: t(labelKey) }));
  });

  return el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h2', { text: t('model.config') })),
    el('div', { class: 'grid grid-2' },
      el('div', { class: 'field' },
        el('label', { text: t('model.time_column') }), timeSel,
        el('div', { class: 'hint', text: t('model.time_column_hint') })),
      el('div', { class: 'field' }, el('label', { text: t('model.metric') }), metricSel),
      el('div', { class: 'field' }, budgetLbl, budget,
        el('div', { class: 'hint', text: t('model.budget_hint') })),
      el('div', { class: 'field' }, modelsLbl, models)),
    el('div', { class: 'grid grid-2' },
      el('div', { class: 'field' }, el('label', { text: t('model.exclude_columns') }), excludeSel),
      el('div', { class: 'field' }, el('label', { text: t('common.advanced') }),
        el('div', { style: 'display:flex;flex-direction:column;gap:10px' }, ...toggles))),
    familiesBlock());
}

export default {
  mount(host, { go }) { nav = go; this.host = host; },
  async refresh() {
    const host = this.host;
    const s = store.get();
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('model.title') }),
      el('p', { class: 'page-lead', text: t('model.lead') })));

    if (!s.datasetId) {
      host.appendChild(emptyState(t('errors.no_dataset')));
      host.appendChild(el('button', { class: 'btn btn-primary mt-2', onClick: () => nav('data') }, t('nav.data')));
      return;
    }

    host.appendChild(el('div', { class: 'note accent' },
      el('div', { class: 'strong mb-1', text: t('model.protocol_title') }),
      el('div', { class: 'small', text: t('model.protocol_text') })));

    const analysisHost = el('div');
    const configHost = el('div');
    const runHost = el('div');

    const onTarget = async () => {
      const target = store.get().target;
      clear(configHost); clear(analysisHost);
      if (!target) return;
      configHost.appendChild(configCard());
      analysisHost.appendChild(await targetAnalysis(store.get().datasetId, target));
      renderRun();
    };

    host.appendChild(objectiveCard(onTarget));
    host.appendChild(analysisHost);
    host.appendChild(configHost);
    host.appendChild(runHost);

    const self = this;
    function renderRun() {
      clear(runHost);
      const job = jobPanel();
      job.root.classList.add('hidden');
      const btn = el('button', { class: 'btn btn-primary' }, t('model.train'));
      btn.onclick = async () => {
        const st = store.get();
        if (!st.target) { toast(t('errors.no_target'), 'warn'); return; }
        btn.disabled = true;
        btn.textContent = t('model.training');
        job.root.classList.remove('hidden');
        job.reset();
        audio.beep('start');
        try {
          const r = await api.runJob('/api/automl/train', {
            dataset_id: st.datasetId, target: st.target, ...cfg,
          }, (j) => job.update(j));
          store.set({ modelId: r.model_id, report: r.report });
          await store.refreshModels();
          audio.beep('done');
          const ch = r.report.champion;
          const line = `${t('results.champion')}: ${ch.model}. ${r.report.metric} ${dec(ch.holdout[r.report.metric], 4)} ${t('results.holdout_window')}.`;
          audio.speak(line);
          toast(line, 'ok', t('common.success'), 8000);
          nav('results');
        } catch (err) {
          if (err.message !== 'CANCELLED') fail(err);
        } finally { btn.disabled = false; btn.textContent = t('model.train'); }
      };
      runHost.appendChild(el('div', { class: 'card' }, el('div', { class: 'row' }, btn), job.root));
    }

    if (s.target && store.columns().includes(s.target)) await onTarget();
  },
};
