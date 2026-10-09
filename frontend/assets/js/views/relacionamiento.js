/**
 * Relacionamiento con consentimiento.
 *
 * La base es propia: gente que eligió entrar y consintió, por finalidad, que
 * la contacten, que le manden comunicaciones comerciales, que se usen datos de
 * su salud y que se le personalice el contenido. Sobre esa base, el
 * «siguiente mejor contenido» de cada persona —como recomienda un marketplace—
 * pero sólo entre lo que la ley y el consentimiento permiten enviarle.
 *
 * Las fuentes públicas (censo, prevalencias, escucha social) entran agregadas:
 * dicen dónde está el mercado que la base todavía no alcanza y de qué se habla,
 * nunca quién.
 */
import * as api from '../api.js';
import { t, num, pct } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import * as charts from '../charts.js';
import { el, clear, note, emptyState, fail, icon, table, stat, badge } from '../ui.js';

const TABLAS = ['contactos', 'contenidos', 'interacciones', 'poblacion', 'prevalencias', 'escucha'];
const OBLIGATORIAS = ['contactos', 'contenidos'];
const PISTAS = { contactos: /contacto/i, contenidos: /contenido/i, interacciones: /interacc/i,
  poblacion: /censo|poblaci/i, prevalencias: /prevalen/i, escucha: /escucha/i };
const ETAPAS = ['captados', 'contactables', 'con_marketing', 'con_salud', 'con_perfilado', 'alcanzados', 'activos', 'convertidos'];
const cfg = { area: '', temas: '', por_barrio: false, segmentar: [], por_contacto: 3,
  ids: Object.fromEntries(TABLAS.map((k) => [k, ''])) };

const campo = (label, input) => el('div', { class: 'field' }, el('label', { text: label }), input);
const tasa = (v) => (v == null ? '' : pct(v, 1));
const entero = (v) => (typeof v === 'number' ? num(v) : v ?? '');

function sel(opciones, valor, onchange) {
  const s = el('select', {}, ...opciones.map(([v, txt]) => el('option', { value: v, text: txt, selected: v === valor })));
  s.onchange = (e) => onchange(e.target.value);
  return s;
}

// «Hipertensión: presión alta, hipertensión; Obesidad: obesidad, sobrepeso» → { tema: [términos] }
function leerTemas(texto) {
  const out = {};
  texto.split(';').forEach((parte) => {
    const [tema, terminos = ''] = parte.split(':');
    const lista = terminos.split(',').map((x) => x.trim()).filter(Boolean);
    if (tema.trim()) out[tema.trim()] = lista.length ? lista : [tema.trim()];
  });
  return out;
}

function casilla(texto, marcada, onchange) {
  const i = el('input', { type: 'checkbox' });
  i.checked = marcada;
  i.onchange = () => onchange(i.checked);
  return el('label', { class: 'rel-check' }, i, ` ${texto}`);
}

export default {
  mount(host) { this.host = host; },

  refresh() {
    const host = clear(this.host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('rel.title') }), el('p', { class: 'page-lead', text: t('rel.lead') })));
    host.appendChild(note(t('rel.principio'), 'info'));
    const s = store.get();
    if (!s.datasets.length) { host.appendChild(emptyState(t('errors.no_dataset'), t('rel.sin_datos'))); return; }
    this.salida = el('div');
    this.exportHost = el('div');
    host.appendChild(this.formulario(s));
    host.appendChild(this.salida);
  },

  formulario(s) {
    const datasets = s.datasets.map((d) => [d.id, d.name]);
    const tablas = TABLAS.map((k) => {
      if (cfg.ids[k] && !datasets.some(([id]) => id === cfg.ids[k])) cfg.ids[k] = '';
      // Si un dataset se llama como la tabla (p. ej. «relacionamiento_contactos»), se propone solo.
      if (!cfg.ids[k]) cfg.ids[k] = (s.datasets.find((d) => PISTAS[k].test(d.name)) || {}).id || '';
      const primera = ['', t(OBLIGATORIAS.includes(k) ? 'rel.elegir' : 'rel.ninguna')];
      return campo(t(`rel.tabla_${k}`), sel([primera, ...datasets], cfg.ids[k], (v) => { cfg.ids[k] = v; }));
    });
    const area = el('input', { type: 'text', value: cfg.area, placeholder: t('rel.area_ph') });
    area.oninput = () => { cfg.area = area.value; };
    const temas = el('input', { type: 'text', value: cfg.temas, placeholder: t('rel.temas_ph') });
    temas.oninput = () => { cfg.temas = temas.value; };
    const porContacto = el('input', { type: 'number', min: 1, max: 10, value: String(cfg.por_contacto) });
    porContacto.oninput = () => { cfg.por_contacto = Math.min(10, Math.max(1, Number(porContacto.value) || 3)); };
    const seg = el('div', { class: 'row' }, ...['sexo', 'rango_edad', 'nse'].map((k) => casilla(t(`rel.seg_${k}`),
      cfg.segmentar.includes(k), (on) => { cfg.segmentar = on ? [...cfg.segmentar, k] : cfg.segmentar.filter((x) => x !== k); })),
    casilla(t('rel.por_barrio'), cfg.por_barrio, (on) => { cfg.por_barrio = on; }));
    const plantilla = sel([['', t('rel.plantillas')], ...TABLAS.map((k) => [k, t(`rel.tabla_${k}`)])], '', (v) => {
      if (v) window.location.href = api.withWorkspace(`/api/relacionamiento/plantilla/${v}`);
    });
    const analizar = el('button', { class: 'btn btn-primary' }, icon('results', 15), t('rel.analizar'));
    analizar.onclick = () => this.analizar(analizar);
    const exportar = el('button', { class: 'btn' }, icon('download', 15), t('rel.exportar'));
    exportar.onclick = () => this.exportar(exportar);
    return el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('div', {}, el('h2', { text: t('rel.fuentes') }),
        el('div', { class: 'card-sub', text: t('rel.fuentes_sub') }))),
      el('div', { class: 'grid grid-3' }, ...tablas),
      el('div', { class: 'grid grid-3' }, campo(t('rel.area'), area), campo(t('rel.por_contacto'), porContacto),
        campo(t('rel.plantilla'), plantilla)),
      campo(t('rel.temas'), temas),
      campo(t('rel.segmentar'), seg),
      el('div', { class: 'row' }, analizar, exportar), this.exportHost);
  },

  cuerpo() {
    const b = { por_contacto: cfg.por_contacto, por_barrio: cfg.por_barrio, segmentar: cfg.segmentar };
    TABLAS.forEach((k) => { if (cfg.ids[k]) b[`${k}_dataset_id`] = cfg.ids[k]; });
    if (cfg.area.trim()) b.area = cfg.area.trim();
    const temas = leerTemas(cfg.temas);
    if (Object.keys(temas).length) b.temas = temas;
    return b;
  },

  faltan() {
    const f = OBLIGATORIAS.filter((k) => !cfg.ids[k]);
    if (f.length) clear(this.exportHost).appendChild(note(t('rel.faltan'), 'warn'));
    return f.length > 0;
  },

  async analizar(btn) {
    if (this.faltan()) return;
    btn.disabled = true;
    clear(this.exportHost);
    const out = clear(this.salida);
    out.appendChild(note(t('common.loading'), 'info'));
    try {
      const r = await api.post('/api/relacionamiento/analizar', this.cuerpo());
      audio.beep('done');
      this.pintar(r);
    } catch (err) { clear(out); fail(err); } finally { btn.disabled = false; }
  },

  async exportar(btn) {
    if (this.faltan()) return;
    btn.disabled = true;
    try {
      const r = await api.post('/api/relacionamiento/exportar', { ...this.cuerpo(), formato: 'csv' });
      clear(this.exportHost).appendChild(el('div', {},
        el('a', { class: 'btn btn-primary mt-1', href: api.withWorkspace(r.download_url), download: '' },
          icon('download', 15), t('common.download')),
        el('p', { class: 'hint', text: t('rel.exportar_hint') })));
    } catch (err) { fail(err); } finally { btn.disabled = false; }
  },

  pintar(r) {
    const out = clear(this.salida);
    r.avisos.forEach((a) => out.appendChild(note(a, 'warn')));
    const tot = r.embudo.find((x) => x.pais === 'Total') || {};
    const irregulares = r.envios_no_elegibles.reduce((s, x) => s + x.envios, 0);
    out.appendChild(el('div', { class: 'grid grid-3' },
      stat(t('rel.contactos'), num(r.resumen.contactos), `${pct(tot.tasa_contactable ?? 0, 0)} ${t('rel.contactables')}`),
      stat(t('rel.recomendaciones'), num(r.resumen.recomendaciones),
        `${num(r.resumen.personas_con_recomendacion)} ${t('rel.personas')} · ${num(r.resumen.personalizadas)} ${t('rel.personalizadas')}`),
      stat(t('rel.cumplimiento'), num(irregulares), t('rel.cumplimiento_sub'), irregulares ? 'bad' : 'ok')));
    out.appendChild(el('div', { class: 'grid grid-2' },
      el('div', { class: 'card' }, el('div', { class: 'card-head' }, el('h2', { text: t('rel.embudo') })),
        charts.hbars(ETAPAS.map((e) => ({ label: t(`rel.etapa_${e}`), value: tot[e] || 0 })), { fmt: (v) => num(v), maxItems: 8 })),
      el('div', { class: 'card' }, el('div', { class: 'card-head' }, el('h2', { text: t('rel.bloqueos') })),
        charts.hbars(this.porMotivo(r.bloqueos), { fmt: (v) => num(v), maxItems: 12 }),
        el('p', { class: 'hint', text: t('rel.bloqueos_hint') }))));
    out.appendChild(this.tarjeta(t('rel.recomendaciones_titulo'), t('rel.recomendaciones_sub'), table([
      { key: 'id_contacto', label: t('rel.contacto'), mono: true, width: '96px' }, { key: 'rango', label: '#', align: 'right' },
      { key: 'titulo', label: t('rel.contenido') }, { key: 'tipo', label: t('rel.tipo'), render: (v) => badge(t(`rel.tipo_${v}`)) },
      { key: 'puntaje', label: t('rel.puntaje'), align: 'right', format: (v) => num(v, 2) },
      { key: 'personalizado', label: t('rel.personalizado'), render: (v) => badge(v ? t('rel.si') : t('rel.no'), v ? 'ok' : '') },
      { key: 'motivo', label: t('rel.por_que') },
    ], r.recomendaciones.slice(0, 200), { compact: true, maxHeight: '360px' })));
    out.appendChild(this.tarjeta(t('rel.kpis'), '', table([
      { key: 'titulo', label: t('rel.contenido') }, { key: 'tipo', label: t('rel.tipo'), render: (v) => badge(t(`rel.tipo_${v}`)) },
      { key: 'envios', label: t('rel.envios'), align: 'right', format: entero },
      { key: 'tasa_apertura', label: t('rel.apertura'), align: 'right', format: tasa },
      { key: 'ctr', label: 'CTR', align: 'right', format: tasa },
      { key: 'tasa_conversion', label: t('rel.conversion'), align: 'right', format: tasa },
      { key: 'tasa_baja', label: t('rel.baja'), align: 'right', format: tasa },
      { key: 'tasa_queja', label: t('rel.queja'), align: 'right', format: tasa },
    ], r.contenidos, { compact: true })));
    if (r.envios_no_elegibles.length) {
      out.appendChild(this.tarjeta(t('rel.irregulares'), t('rel.irregulares_sub'), table([
        { key: 'id_contenido', label: t('rel.contenido'), mono: true }, { key: 'descripcion', label: t('rel.motivo') },
        { key: 'envios', label: t('rel.envios'), align: 'right', format: entero }], r.envios_no_elegibles, { compact: true, maxHeight: '280px' })));
    }
    if (r.cobertura.length) this.pintarCobertura(out, r);
    if (r.escucha_menciones.length || r.farmacovigilancia.length) this.pintarEscucha(out, r);
    out.appendChild(this.tarjeta(t('rel.politicas'), t('rel.politicas_sub'), table([
      { key: 'pais', label: t('rel.pais') }, { key: 'ley_datos', label: t('rel.ley') },
      { key: 'autoridad_sanitaria', label: t('rel.autoridad') },
      { key: 'promocion_receta_a_publico', label: t('rel.rx_publico'), render: (v) => badge(v ? t('rel.si') : t('rel.no'), v ? 'warn' : 'ok') },
      { key: 'frecuencia_max_30d', label: t('rel.frecuencia'), align: 'right' },
      { key: 'validado_por_legal', label: t('rel.validado'), render: (v) => badge(v ? t('rel.si') : t('rel.a_validar'), v ? 'ok' : 'warn') },
    ], r.politicas, { compact: true })));
  },

  porMotivo(bloqueos) {
    const suma = {};
    bloqueos.forEach((b) => { suma[b.motivo] = (suma[b.motivo] || 0) + b.pares; });
    return Object.entries(suma).sort((a, b) => b[1] - a[1]).map(([m, value]) => ({ label: t(`rel.mot_${m}`), value }));
  },

  pintarCobertura(out, r) {
    const cols = ['pais', 'ciudad', 'barrio', 'sexo', 'rango_edad', 'nse'].filter((k) => k in r.cobertura[0]);
    out.appendChild(this.tarjeta(`${t('rel.cobertura')} · ${r.cobertura[0].area_terapeutica}`,
      r.cobertura_resumen?.texto || '', table([
        ...cols.map((k) => ({ key: k, label: t(`rel.col_${k}`) })),
        { key: 'casos_estimados', label: t('rel.casos'), align: 'right', format: entero },
        { key: 'en_base', label: t('rel.en_base'), align: 'right', format: entero },
        { key: 'captados_area', label: t('rel.captados'), align: 'right', format: entero },
        { key: 'penetracion', label: t('rel.penetracion'), align: 'right', format: (v) => (v == null ? '' : pct(v, 3)) },
        { key: 'brecha', label: t('rel.brecha'), align: 'right', format: entero },
      ], r.cobertura.slice(0, 100), { compact: true, maxHeight: '360px' })));
  },

  pintarEscucha(out, r) {
    const porTema = {};
    r.escucha_menciones.forEach((m) => {
      const x = porTema[m.tema] || (porTema[m.tema] = { tema: m.tema, menciones: 0, positivas: 0, negativas: 0 });
      x.menciones += m.menciones; x.positivas += m.positivas; x.negativas += m.negativas;
    });
    const temas = Object.values(porTema).sort((a, b) => b.menciones - a.menciones);
    out.appendChild(el('div', { class: 'grid grid-2' },
      el('div', { class: 'card' }, el('div', { class: 'card-head' }, el('div', {}, el('h2', { text: t('rel.escucha') }),
        el('div', { class: 'card-sub', text: t('rel.escucha_sub') }))),
      charts.hbars(temas.map((x) => ({ label: x.tema, value: x.menciones })), { fmt: (v) => num(v) })),
      el('div', { class: 'card' }, table([
        { key: 'tema', label: t('rel.tema') }, { key: 'menciones', label: t('rel.menciones'), align: 'right', format: entero },
        { key: 'positivas', label: t('rel.positivas'), align: 'right', format: entero },
        { key: 'negativas', label: t('rel.negativas'), align: 'right', format: entero }], temas, { compact: true }))));
    if (r.farmacovigilancia.length) {
      out.appendChild(this.tarjeta(t('rel.farmaco'), t('rel.farmaco_sub'), table([
        { key: 'producto', label: t('rel.producto') },
        { key: 'menciones_posible_evento_adverso', label: t('rel.menciones'), align: 'right', format: entero }],
      r.farmacovigilancia, { compact: true })));
    }
  },

  tarjeta(titulo, sub, cuerpo) {
    return el('div', { class: 'card' }, el('div', { class: 'card-head' }, el('div', {}, el('h2', { text: titulo }),
      sub ? el('div', { class: 'card-sub', text: sub }) : null)), cuerpo);
  },
};
