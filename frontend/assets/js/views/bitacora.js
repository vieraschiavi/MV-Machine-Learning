/**
 * Bitácora: qué se le hizo a los datos, en orden y contado dos veces.
 *
 * La misma información que ya vivía repartida en ETL, Modelado y Resultados,
 * puesta en una sola línea de tiempo y con dos lecturas por paso: la técnica,
 * para auditar, y la criolla, para entender. Se puede llevar en HTML, en Word
 * o en PDF —el PDF sale de imprimir el mismo documento, así los tres formatos
 * dicen exactamente lo mismo—.
 */
import * as api from '../api.js';
import { withWorkspace } from '../api.js';
import { t } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import { el, clear, note, emptyState, fail, toast, icon } from '../ui.js';

const ETAPAS = ['ingesta', 'etl', 'objetivo', 'particion', 'preparacion', 'entrenamiento',
  'seleccion', 'calibracion', 'evaluacion', 'explicacion', 'veredicto'];

let nav = null;

/** Fuente elegida: se conserva entre visitas a la pestaña. */
const fuente = { dataset: null, modelo: null, lectura: 'ambas' };

function etapaLabel(etapa) {
  return ETAPAS.includes(etapa) ? t(`bit.etapa_${etapa}`) : etapa;
}

function tarjeta(valor, etiqueta) {
  return el('div', { class: 'bit-tarjeta' },
    el('b', { text: valor === null || valor === undefined ? '—' : String(valor) }),
    el('span', { text: etiqueta }));
}

function paso(p) {
  const evidencia = (p.evidencia || []).length
    ? el('table', { class: 'bit-evidencia' },
      ...p.evidencia.map((e) => el('tr', {},
        el('th', { text: e.clave }), el('td', { text: e.valor }))))
    : null;

  const detalle = String(p.detalle || '').trim()
    ? el('details', { class: 'bit-detalle' },
      el('summary', { text: t('bit.detail') }), el('pre', { text: p.detalle }))
    : null;

  return el('section', { class: 'bit-paso', dataset: { etapa: p.etapa } },
    el('div', { class: 'bit-cabeza' },
      el('span', { class: 'bit-orden', text: String(p.orden) }),
      el('span', { class: 'bit-etapa', text: etapaLabel(p.etapa) }),
      el('h3', { text: p.titulo })),
    el('div', { class: 'bit-dos' },
      el('div', { class: 'bit-caja bit-tec' },
        el('em', { text: t('bit.tech') }), el('p', { text: p.tecnico })),
      el('div', { class: 'bit-caja bit-cri' },
        el('em', { text: t('bit.plain') }), el('p', { text: p.criollo }))),
    el('p', { class: 'bit-linea' }, el('b', { text: `${t('bit.why')}: ` }), p.porque),
    el('p', { class: 'bit-linea' }, el('b', { text: `${t('bit.impact')}: ` }), p.impacto),
    ...(evidencia ? [evidencia] : []),
    ...(detalle ? [detalle] : []));
}

export default {
  mount(host, { go }) { nav = go; this.host = host; },

  async refresh() {
    const host = this.host;
    const s = store.get();
    clear(host);

    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('bit.title') }),
      el('p', { class: 'page-lead', text: t('bit.lead') })));

    if (!s.datasets.length && !s.models.length) {
      host.appendChild(emptyState(t('errors.no_dataset')));
      return;
    }

    /* ── de dónde se arma ─────────────────────────────────────────────── */
    const dsSel = el('select', {},
      el('option', { value: '', text: `— ${t('common.none')} —` }),
      ...s.datasets.map((d) => el('option', {
        value: d.id, text: d.name,
        selected: d.id === (fuente.dataset || s.datasetId) })));
    const mdSel = el('select', {},
      el('option', { value: '', text: `— ${t('common.none')} —` }),
      ...s.models.map((m) => el('option', {
        value: m.id, text: m.name, selected: m.id === fuente.modelo })));
    const lectura = el('select', {},
      ...[['ambas', 'bit.reading_both'], ['tecnica', 'bit.reading_tech'],
        ['criolla', 'bit.reading_plain']].map(([v, k]) => el('option', {
        value: v, text: t(k), selected: v === fuente.lectura })));

    const salida = el('div', { class: 'bit-salida' });
    const self = this;

    const cargar = async () => {
      fuente.dataset = dsSel.value || null;
      fuente.modelo = mdSel.value || null;
      if (!fuente.dataset && !fuente.modelo) {
        clear(salida).appendChild(emptyState(t('bit.pick_source')));
        return;
      }
      clear(salida).appendChild(note(t('common.loading'), 'info'));
      try {
        const q = new URLSearchParams();
        if (fuente.dataset) q.set('dataset_id', fuente.dataset);
        if (fuente.modelo) q.set('model_id', fuente.modelo);
        self.libro = await api.get(`/api/bitacora?${q}`);
        self.pintar(salida);
      } catch (err) { clear(salida); fail(err); }
    };

    dsSel.onchange = cargar;
    mdSel.onchange = cargar;
    lectura.onchange = () => {
      fuente.lectura = lectura.value;
      salida.dataset.lectura = lectura.value;
    };
    salida.dataset.lectura = fuente.lectura;

    host.appendChild(el('div', { class: 'card' },
      el('div', { class: 'grid grid-3' },
        el('div', { class: 'field' }, el('label', { text: t('nav.data') }), dsSel),
        el('div', { class: 'field' }, el('label', { text: t('results.saved_models') }), mdSel),
        el('div', { class: 'field' }, el('label', { text: t('bit.reading') }), lectura)),
      el('div', { class: 'row' },
        el('button', { class: 'btn', onClick: cargar }, icon('refresh', 15), t('common.refresh')),
        el('button', { class: 'btn', onClick: () => self.exportar('html') },
          icon('download', 15), t('bit.export_html')),
        el('button', { class: 'btn', onClick: () => self.exportar('docx') },
          icon('download', 15), t('bit.export_word')),
        el('button', { class: 'btn btn-primary', onClick: () => self.pdf() },
          icon('file', 15), t('bit.save_pdf')))));

    host.appendChild(salida);
    await cargar();
  },

  /* ── pintado ─────────────────────────────────────────────────────────── */
  pintar(salida) {
    const libro = this.libro;
    clear(salida);
    if (!libro || !libro.pasos.length) {
      salida.appendChild(emptyState(t('bit.empty')));
      return;
    }
    const r = libro.resumen || {};
    salida.appendChild(el('div', { class: 'bit-tarjetas' },
      tarjeta(r.n_pasos, t('bit.steps')),
      tarjeta(r.transformaciones, t('bit.transformations')),
      tarjeta(r.filas_inicio, t('bit.rows_start')),
      tarjeta(r.filas_fin, t('bit.rows_end')),
      tarjeta(r.columnas_inicio, t('bit.cols_start')),
      tarjeta(r.columnas_fin, t('bit.cols_end'))));

    salida.appendChild(el('div', { class: 'bit-como' },
      el('b', { text: `${t('bit.how_to_read_title')} ` }), t('bit.how_to_read')));

    libro.pasos.forEach((p) => salida.appendChild(paso(p)));
  },

  /* ── salidas ─────────────────────────────────────────────────────────── */
  async exportar(formato) {
    if (!fuente.dataset && !fuente.modelo) { toast(t('bit.pick_source'), 'warn'); return; }
    try {
      const r = await api.post('/api/bitacora/exportar', {
        dataset_id: fuente.dataset, model_id: fuente.modelo, formato,
      });
      audio.beep('done');
      const a = el('a', { href: withWorkspace(r.download_url), download: r.filename });
      document.body.appendChild(a); a.click(); a.remove();
      toast(r.filename, 'ok', t('common.success'));
    } catch (err) { fail(err); }
  },

  /**
   * El PDF es este mismo documento impreso: en el escritorio lo guarda
   * Electron sin diálogo de impresora; en el navegador se abre el cuadro de
   * impresión con «Guardar como PDF» ya disponible. No hay una segunda
   * maqueta que pueda quedar desincronizada de la primera.
   */
  async pdf() {
    if (!fuente.dataset && !fuente.modelo) { toast(t('bit.pick_source'), 'warn'); return; }
    let url;
    try {
      const r = await api.post('/api/bitacora/exportar', {
        dataset_id: fuente.dataset, model_id: fuente.modelo, formato: 'html',
      });
      url = withWorkspace(r.download_url);
    } catch (err) { fail(err); return; }

    if (window.mvDesktop && window.mvDesktop.guardarPDF) {
      try {
        const res = await window.mvDesktop.guardarPDF(url, 'MV-Bitacora.pdf');
        if (res && res.ok) { audio.beep('done'); toast(res.path, 'ok', t('common.success')); }
        else if (res && res.error) { toast(res.error, 'warn'); }
        return;
      } catch { /* si el puente falla, queda la impresión del navegador */ }
    }

    const marco = el('iframe', { class: 'bit-impresion', src: url });
    marco.onload = () => {
      try { marco.contentWindow.focus(); marco.contentWindow.print(); } catch { /* bloqueado */ }
      setTimeout(() => marco.remove(), 60_000);
    };
    document.body.appendChild(marco);
    toast(t('bit.print_hint'), 'info');
  },
};
