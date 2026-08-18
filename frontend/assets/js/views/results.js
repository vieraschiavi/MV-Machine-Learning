/** Resultados: métricas del holdout, comparativa, variables y diagnóstico. */
import * as api from '../api.js';
import * as charts from '../charts.js';
import { t, num, pct, dec, when } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import { el, clear, table, badge, note, emptyState, fail, toast, metricValue, severityKind,
  jobPanel, icon } from '../ui.js';

let nav = null;
let tab = 'metrics';

function championCard(r) {
  const ch = r.champion;
  const primary = ch.holdout[r.metric];
  const kind = severityKind(r.verdict.level);
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {},
        el('h2', { text: t('results.champion') }),
        el('div', { class: 'card-sub mono', text: ch.model })),
      badge(t(`model.task_${r.task}`), 'accent'),
      ch.calibrated ? badge(t('results.calibrated'), 'ok') : null),
    el('div', { class: 'grid grid-4' },
      el('div', { class: `stat ${kind}` },
        el('div', { class: 'stat-label', text: `${r.metric} · ${t('results.holdout_window')}` }),
        el('div', { class: 'stat-value', text: metricValue(r.metric, primary) }),
        el('div', { class: 'stat-sub', text: r.metric_info.explanation })),
      el('div', { class: 'stat' },
        el('div', { class: 'stat-label', text: t('results.selection_window') }),
        el('div', { class: 'stat-value', text: metricValue(r.metric, ch.selection[r.metric]) })),
      el('div', { class: `stat ${(ch.gap ?? 0) > 0.05 ? 'warn' : 'ok'}` },
        el('div', { class: 'stat-label', text: t('results.degradation') }),
        el('div', { class: 'stat-value', text: ch.gap == null ? '—' : dec(ch.gap, 4) })),
      el('div', { class: 'stat' },
        el('div', { class: 'stat-label', text: t('common.rows') }),
        el('div', { class: 'stat-value', text: num(r.rows_used) }),
        el('div', { class: 'stat-sub',
          text: `${r.split.train} / ${r.split.selection} / ${r.split.holdout} · ${r.split.mode}` }))),
    el('div', { class: 'mt-2' },
      ...r.verdict.notes.map((n) => note(n.text, severityKind(n.level)))));
}

function metricsPanel(r) {
  const rows = Object.entries(r.champion.holdout)
    .filter(([k]) => !['n', 'threshold', 'positive_rate'].includes(k))
    .map(([k, v]) => ({ metric: k, holdout: v, selection: r.champion.selection[k] }));
  return el('div', {},
    table([
      { key: 'metric', label: t('results.metrics'), mono: true },
      { key: 'holdout', label: t('results.holdout_window'), align: 'right',
        render: (v, row) => el('span', { class: 'strong', text: metricValue(row.metric, v) }) },
      { key: 'selection', label: t('results.selection_window'), align: 'right',
        render: (v, row) => metricValue(row.metric, v) },
    ], rows),
    el('div', { class: 'card mt-2' },
      el('div', { class: 'card-head' }, el('h3', { text: t('model.protocol_title') })),
      el('dl', { class: 'kv' },
        el('dt', { text: t('model.time_column') }),
        el('dd', { text: r.split.time_column || `— (${r.split.mode})` }),
        el('dt', { text: t('model.feature_selection') }),
        el('dd', { text: r.feature_selection?.applied
          ? `${r.n_features_in} → ${r.feature_selection.kept.length} · ${r.feature_selection.reason}`
          : (r.feature_selection?.reason || t('common.no')) }),
        el('dt', { text: 'Transformación del objetivo' }),
        el('dd', { text: r.target_transform.log
          ? `logarítmica · smearing ${dec(r.target_transform.smearing, 4)}` : t('common.none') }),
        el('dt', { text: t('common.seconds') }), el('dd', { text: num(r.seconds, 1) }))));
}

function leaderboardPanel(r) {
  const metric = r.metric;
  return el('div', {},
    note(t('results.lead'), 'accent'),
    table([
      { key: 'model', label: t('results.champion'), mono: true, width: '220px' },
      { key: 'type', label: t('common.type'), render: (v) => badge(v, v === 'ensemble' ? 'accent' : '') },
      { key: (row) => row.selection[metric], label: `${metric} · ${t('results.selection_window')}`,
        align: 'right', format: (v) => metricValue(metric, v) },
      { key: (row) => row.holdout[metric], label: `${metric} · ${t('results.holdout_window')}`,
        align: 'right', render: (v) => el('span', { class: 'strong', text: metricValue(metric, v) }) },
      { key: 'n_trials', label: 'Configuraciones', align: 'right', format: (v) => num(v) },
      { key: 'calibrated', label: t('results.calibrated'), render: (v) => (v ? badge(t('common.yes'), 'ok') : '—') },
    ], r.leaderboard),
    charts.bars(r.leaderboard.map((b) => ({
      label: b.model.replace(/^ensemble\(.*/, 'ensemble'),
      value: b.holdout[metric] ?? 0, sel: b.selection[metric] ?? 0,
    })), {
      title: `${metric}: ${t('results.holdout_window')} vs ${t('results.selection_window')}`,
      width: 680, height: 240, second: 'sel', fmtY: (v) => v.toFixed(2),
    }));
}

function variablesPanel(r) {
  const f = r.features;
  const box = el('div', {});
  if (f.narrative?.length) {
    box.appendChild(el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h3', { text: t('results.variables') })),
      ...f.narrative.map((x) => el('p', { class: 'small', text: x }))));
  }
  const withPerm = f.ranking.filter((x) => x.permutation_drop_pct != null);
  if (withPerm.length) {
    box.appendChild(charts.hbars(
      withPerm.map((x) => ({ label: x.column, value: x.permutation_drop_pct })),
      { title: `${t('results.permutation')} (%)`, width: 680, fmt: (v) => `${v.toFixed(2)}%`, maxItems: 18 }));
  }
  box.appendChild(el('div', { class: 'mt-2' }, table([
    { key: 'column', label: t('common.column'), mono: true },
    { key: 'permutation_drop_pct', label: `${t('results.permutation')} %`, align: 'right',
      format: (v) => (v == null ? '—' : `${dec(v, 2)}%`) },
    { key: 'permutation_drop', label: t('results.permutation'), align: 'right',
      format: (v) => (v == null ? '—' : dec(v, 5)) },
    { key: 'native', label: t('results.native_importance'), align: 'right', format: (v) => dec(v, 4) },
    { key: 'shap_mean_abs', label: t('results.shap_value'), align: 'right',
      format: (v) => (v == null ? '—' : dec(v, 4)) },
    { key: 'shap_direction', label: t('results.shap_direction'), format: (v) => v || '—' },
  ], f.ranking, { maxHeight: '520px' })));
  (f.method_notes || []).forEach((n) => box.appendChild(note(n)));
  return box;
}

function diagnosticsPanel(r) {
  const d = r.diagnostics || {};
  const box = el('div', {});
  if (r.task === 'binary') {
    if (d.deciles?.length) {
      box.appendChild(el('div', { class: 'grid grid-2' },
        charts.bars(d.deciles.map((x) => ({ label: `D${x.decil}`, value: x.lift })),
          { title: t('results.concentration'), width: 460, height: 220,
            fmtY: (v) => `${v.toFixed(1)}x` }),
        charts.line([d.deciles.map((x) => [x.decil, x.captura_acum * 100])],
          { title: t('results.capture'), width: 460, height: 220,
            fmtX: (v) => v.toFixed(0), fmtY: (v) => `${v.toFixed(0)}%` })));
      box.appendChild(table([
        { key: 'decil', label: t('results.decile'), align: 'right' },
        { key: 'n', label: t('results.cases'), align: 'right', format: (v) => num(v) },
        { key: 'positivos', label: t('results.positives'), align: 'right', format: (v) => num(v) },
        { key: 'prob_media', label: t('results.mean_prob'), align: 'right', format: (v) => pct(v, 2) },
        { key: 'tasa_real', label: t('results.real_rate'), align: 'right', format: (v) => pct(v, 2) },
        { key: 'lift', label: t('results.lift'), align: 'right', format: (v) => `${dec(v, 2)}x` },
        { key: 'captura_acum', label: t('results.capture'), align: 'right', format: (v) => pct(v, 1) },
      ], d.deciles));
    }
    const curves = el('div', { class: 'grid grid-2 mt-2' });
    if (d.roc?.length) {
      curves.appendChild(charts.line([d.roc.map((p) => [p.fpr, p.tpr])], {
        title: t('results.roc_curve'), width: 440, height: 260, diagonal: true,
        fmtX: (v) => v.toFixed(1), fmtY: (v) => v.toFixed(1), xmin: 0, xmax: 1, ymin: 0, ymax: 1,
      }));
    }
    if (d.calibration?.length) {
      curves.appendChild(charts.line([
        d.calibration.map((p) => [p.predicha, p.observada]),
      ], {
        title: t('results.calibration_curve'), width: 440, height: 260, diagonal: true,
        fmtX: (v) => v.toFixed(2), fmtY: (v) => v.toFixed(2),
        labels: [`${t('results.observed')} vs ${t('results.predicted')}`],
      }));
    }
    box.appendChild(curves);
    if (d.confusion) {
      const c = d.confusion;
      box.appendChild(el('div', { class: 'card mt-2' },
        el('div', { class: 'card-head' },
          el('div', {}, el('h3', { text: t('results.confusion') }),
            el('div', { class: 'card-sub', text: `Umbral ${dec(c.umbral, 4)}` }))),
        table([
          { key: 'row', label: '' },
          { key: 'pos', label: t('results.pred_positive'), align: 'right', format: (v) => num(v) },
          { key: 'neg', label: t('results.pred_negative'), align: 'right', format: (v) => num(v) },
        ], [
          { row: t('results.actual_positive'), pos: c.vp, neg: c.fn },
          { row: t('results.actual_negative'), pos: c.fp, neg: c.vn },
        ])));
    }
  } else if (r.task === 'regression') {
    if (d.totals) {
      box.appendChild(el('div', { class: 'grid grid-3 mb-2' },
        el('div', { class: 'stat' }, el('div', { class: 'stat-label', text: 'Total real' }),
          el('div', { class: 'stat-value', text: num(d.totals.real, 0) })),
        el('div', { class: 'stat' }, el('div', { class: 'stat-label', text: 'Total predicho' }),
          el('div', { class: 'stat-value', text: num(d.totals.predicho, 0) })),
        el('div', { class: `stat ${Math.abs(d.totals.desvio_pct || 0) > 5 ? 'warn' : 'ok'}` },
          el('div', { class: 'stat-label', text: 'Desvío del total' }),
          el('div', { class: 'stat-value', text: pct(d.totals.desvio_pct, 2, true) }))));
    }
    if (d.scatter?.length) {
      box.appendChild(charts.scatter(d.scatter.map((p) => [p.real, p.pred]),
        { title: t('results.real_vs_pred'), width: 680, height: 320 }));
    }
    if (d.bins?.length) {
      box.appendChild(charts.bars(d.bins.map((b) => ({ label: `D${b.decil}`, value: b.real, pred: b.pred })),
        { title: `${t('results.observed')} vs ${t('results.predicted')}`, width: 680, height: 240,
          second: 'pred', fmtY: (v) => v.toPrecision(3) }));
      box.appendChild(table([
        { key: 'decil', label: t('results.decile'), align: 'right' },
        { key: 'n', label: t('common.total'), align: 'right', format: (v) => num(v) },
        { key: 'real', label: t('results.observed'), align: 'right', format: (v) => num(v, 2) },
        { key: 'pred', label: t('results.predicted'), align: 'right', format: (v) => num(v, 2) },
      ], d.bins));
    }
  } else if (d.per_class?.length) {
    box.appendChild(table([
      { key: 'clase', label: 'Clase' },
      { key: 'soporte', label: t('results.support'), align: 'right', format: (v) => num(v) },
      { key: 'recall', label: 'Recall', align: 'right', format: (v) => pct(v, 1) },
      { key: 'precision', label: 'Precisión', align: 'right', format: (v) => pct(v, 1) },
    ], d.per_class));
    if (d.confusion_matrix) {
      box.appendChild(charts.heatmap(d.classes || [], d.confusion_matrix.map((row) => {
        const s = row.reduce((a, b) => a + b, 0) || 1;
        return row.map((v) => v / s);
      }), { title: t('results.confusion'), width: 560 }));
    }
  }
  return box.children.length ? box : emptyState(t('common.empty'));
}

function actionsBar(r, host) {
  const narrateBtn = el('button', { class: 'btn' }, icon('ai', 15), t('results.narrate_result'));
  const speakBtn = el('button', { class: 'btn' }, icon('play', 15), t('topbar.narrate'));
  const scoreBtn = el('button', { class: 'btn' }, t('results.score_dataset'));
  const exportBtn = el('button', { class: 'btn btn-primary' }, icon('download', 15), t('export.excel'));
  const out = el('div', { class: 'mt-2' });

  const summary = () => {
    const ch = r.champion;
    const top = (r.features.ranking || []).slice(0, 3).map((x) => x.column).join(', ');
    return `${t('results.champion')}: ${ch.model}. ${r.metric} ${dec(ch.holdout[r.metric], 4)} `
      + `${t('results.holdout_window')}. ${r.verdict.notes.map((n) => n.text).join(' ')} `
      + `${t('results.variables')}: ${top}.`;
  };

  speakBtn.onclick = () => {
    if (audio.isSpeaking()) { audio.stop(); return; }
    if (!audio.speak(summary(), { force: true })) toast(t('audio.no_voices'), 'warn');
  };

  narrateBtn.onclick = async () => {
    narrateBtn.disabled = true;
    clear(out).appendChild(el('div', { class: 'row' }, el('span', { class: 'spinner' })));
    try {
      const lang = document.documentElement.lang || 'es';
      const rr = await api.post('/api/ai/narrate',
        { kind: 'training', lang, model_id: store.get().modelId });
      clear(out).appendChild(el('div', { class: 'card' },
        el('div', { class: 'card-head' },
          el('div', {}, el('h3', { text: t('results.narrate_result') }),
            el('div', { class: 'card-sub', text: `${rr.provider} · ${rr.model}` })),
          el('button', { class: 'btn btn-sm', onClick: () => audio.speak(rr.text, { force: true }) },
            icon('play', 14))),
        ...rr.text.split('\n').filter(Boolean).map((p) => el('p', { text: p }))));
      audio.speak(rr.text);
    } catch (err) { clear(out); fail(err); } finally { narrateBtn.disabled = false; }
  };

  scoreBtn.onclick = async () => {
    const s = store.get();
    const sel = el('select', {}, ...s.datasets.map((d) => el('option', {
      value: d.id, text: `${d.name} · ${num(d.rows)}`, selected: d.id === s.datasetId })));
    const { modal } = await import('../ui.js');
    modal({
      title: t('results.score_dataset'),
      body: el('div', { class: 'field' }, el('label', { text: t('nav.data') }), sel),
      actions: [
        { label: t('common.cancel'), kind: 'ghost' },
        {
          label: t('common.run'), kind: 'primary',
          onClick: async () => {
            const job = jobPanel();
            clear(out).appendChild(el('div', { class: 'card' }, job.root));
            try {
              const rr = await api.runJob('/api/automl/score',
                { model_id: s.modelId, dataset_id: sel.value }, (j) => job.update(j));
              await store.refreshDatasets();
              toast(`${num(rr.rows)} ${t('common.rows')}`, 'ok', t('common.success'));
              audio.beep('done');
              clear(out).appendChild(note(
                `${rr.dataset.name} · ${num(rr.dataset.rows)} ${t('common.rows')}`, 'ok'));
            } catch (err) { fail(err); }
          },
        },
      ],
    });
  };

  exportBtn.onclick = () => nav('export');

  return el('div', { class: 'card' },
    el('div', { class: 'row' }, speakBtn, narrateBtn, scoreBtn, el('span', { class: 'spacer' }), exportBtn),
    out);
}

export default {
  mount(host, { go }) { nav = go; this.host = host; },
  async refresh() {
    const host = this.host;
    const s = store.get();
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('results.title') }),
      el('p', { class: 'page-lead', text: t('results.lead') })));

    if (!s.models.length) {
      host.appendChild(emptyState(t('results.no_model')));
      host.appendChild(el('button', { class: 'btn btn-primary mt-2', onClick: () => nav('model') }, t('nav.model')));
      return;
    }

    const sel = el('select', { style: 'max-width:420px' }, ...s.models.map((m) => el('option', {
      value: m.id, selected: m.id === s.modelId,
      text: `${m.name} · ${m.metric} ${dec(m.score, 4)} · ${when(m.created_at)}`,
    })));
    sel.onchange = async () => { await store.loadReport(sel.value); this.refresh(); };
    host.appendChild(el('div', { class: 'row mb-2' },
      el('div', { class: 'field mb-0', style: 'flex:1' },
        el('label', { text: t('results.saved_models') }), sel)));

    let r = s.report;
    if (!r || s.modelId !== sel.value) {
      try { r = await store.loadReport(sel.value); } catch (err) { fail(err); return; }
    }
    if (!r) { host.appendChild(emptyState(t('results.no_model'))); return; }

    host.appendChild(championCard(r));
    host.appendChild(actionsBar(r, host));

    const tabs = el('div', { class: 'tabs' });
    const panel = el('div');
    [['metrics', t('results.metrics')], ['leaderboard', t('results.leaderboard')],
     ['variables', t('results.variables')], ['diagnostics', t('results.diagnostics')]]
      .forEach(([key, label]) => {
        const b = el('button', { class: `tab ${key === tab ? 'active' : ''}`, text: label });
        b.onclick = () => {
          tab = key;
          Array.from(tabs.children).forEach((c) => c.classList.toggle('active', c === b));
          render(key);
        };
        tabs.appendChild(b);
      });
    host.appendChild(tabs);
    host.appendChild(panel);

    function render(key) {
      clear(panel);
      if (key === 'metrics') panel.appendChild(metricsPanel(r));
      else if (key === 'leaderboard') panel.appendChild(leaderboardPanel(r));
      else if (key === 'variables') panel.appendChild(variablesPanel(r));
      else panel.appendChild(diagnosticsPanel(r));
    }
    render(tab);
  },
};
