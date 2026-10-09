/**
 * Portafolio y mercado.
 *
 * Arriba, la matriz de contribución: quién sostiene el negocio (eje Y), qué
 * tan avanzado está su mix de presentaciones (eje X) y qué conviene proteger,
 * acelerar o desarrollar, con el siguiente motor de cada uno.
 *
 * Abajo, el agente de mercado: el embudo epidemiológico por país —tratados,
 * diagnosticados sin tratamiento y gente con la enfermedad que no consulta—,
 * con supuestos que salen de estudios de mercado o, a falta de ellos, de una
 * propuesta del motor de IA marcada «a validar». La proyección de un
 * lanzamiento sale de ese embudo, y su rango dice cuánto pesa lo que no se sabe.
 */
import * as api from '../api.js';
import { t, num, pct } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import * as charts from '../charts.js';
import { el, clear, note, emptyState, fail, icon, table, stat, badge } from '../ui.js';

const ACCION_KIND = { proteger: 'info', acelerar: 'warn', desarrollar: 'bad' };
const EVIDENCIA_KIND = { estudios: 'ok', mixta: 'warn', 'solo IA': 'bad' };
const cfg = { entidad: null, valor: null, mix: '', grupo: '', periodo: '', etiqueta: 'mercados', grupo_valor: '' };
const ctx = { area_terapeutica: '', molecula: '', enfermedad: '', presentacion: '',
  paises: '', segmentos: 'Hombres, Mujeres', estudios: '', pico: 12, meses: 18, horizonte: 36, forma: 'media' };
let propuesta = null;

function sel(opciones, valor, onchange) {
  const s = el('select', {}, ...opciones.map(([v, txt]) => el('option', { value: v, text: txt, selected: v === valor })));
  s.onchange = (e) => onchange(e.target.value);
  return s;
}
const campo = (label, input) => el('div', { class: 'field' }, el('label', { text: label }), input);
// Millones con una cifra: el eje de los gráficos no tiene lugar para «1.821.709».
const compacto = (v) => (Math.abs(v) >= 1e6 ? `${num(v / 1e6, 1)} M` : num(Math.round(v)));
const lista = (s) => s.split(',').map((x) => x.trim()).filter(Boolean);
function entrada(clave, tipo = 'text') {
  const i = el('input', { type: tipo, value: String(ctx[clave]) });
  i.oninput = () => { ctx[clave] = tipo === 'number' ? Number(i.value) : i.value; };
  return i;
}

export default {
  mount(host) { this.host = host; },

  async refresh() {
    const host = clear(this.host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('port.title') }), el('p', { class: 'page-lead', text: t('port.lead') })));
    const s = store.get();
    if (!s.datasets.length) { host.appendChild(emptyState(t('errors.no_dataset'))); return; }
    this.salidaMatriz = el('div');
    this.salidaMercado = el('div');
    host.appendChild(await this.formMatriz(s));
    host.appendChild(this.salidaMatriz);
    host.appendChild(this.formMercado(s));
    host.appendChild(this.salidaMercado);
  },

  /* ── matriz de contribución ─────────────────────────────────────────── */
  async formMatriz(s) {
    const campos = el('div', { class: 'grid grid-3' });
    const dsSel = sel(s.datasets.map((d) => [d.id, d.name]), s.datasetId, (v) => { store.elegirDataset(v); cargar(); });
    const self = this;
    const cargar = async () => {
      clear(campos);
      let c;
      try { c = await api.get(`/api/portafolio/columnas/${dsSel.value}`); } catch (err) { fail(err); return; }
      const cat = c.categoricas.map((x) => [x, x]);
      const opc = [['', t('port.ninguna')], ...cat];
      cfg.entidad = c.categoricas.includes(cfg.entidad) ? cfg.entidad : c.categoricas[0] || null;
      cfg.valor = c.numericas.includes(cfg.valor) ? cfg.valor : c.numericas[0] || null;
      // Lo elegido para otro dataset no vale en éste: se limpia lo que no existe.
      if (!c.categoricas.includes(cfg.mix)) cfg.mix = '';
      if (!c.categoricas.includes(cfg.grupo)) { cfg.grupo = ''; cfg.grupo_valor = ''; }
      if (![...c.categoricas, ...c.fechas].includes(cfg.periodo)) cfg.periodo = '';
      self.matrizLista = false;
      campos.append(
        campo(t('port.entidad'), sel(cat, cfg.entidad, (v) => { cfg.entidad = v; })),
        campo(t('port.valor'), sel(c.numericas.map((x) => [x, x]), cfg.valor, (v) => { cfg.valor = v; })),
        campo(t('port.mix'), sel(opc, cfg.mix, (v) => { cfg.mix = v; })),
        campo(t('port.grupo'), sel(opc, cfg.grupo, (v) => { cfg.grupo = v; cfg.grupo_valor = ''; })),
        campo(t('port.periodo'), sel([...opc, ...c.fechas.map((x) => [x, x])], cfg.periodo, (v) => { cfg.periodo = v; })),
        campo(t('port.etiqueta'), sel(['mercados', 'moléculas', 'marcas'].map((x) => [x, x]), cfg.etiqueta,
          (v) => { cfg.etiqueta = v; })));
    };
    const btn = el('button', { class: 'btn btn-primary' }, icon('results', 15), t('port.calcular'));
    btn.onclick = () => self.calcularMatriz(dsSel.value, btn);
    const pbi = el('button', { class: 'btn' }, icon('download', 15), t('port.powerbi'));
    pbi.onclick = () => self.descargarPowerBI(dsSel.value, pbi);
    this.pbiHost = el('div');
    await cargar();
    return el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h2', { text: t('port.matriz') })),
      campo(t('nav.data'), dsSel), campos, el('div', { class: 'row' }, btn, pbi), this.pbiHost);
  },

  cuerpoMatriz(ds) {
    const b = { dataset_id: ds, entidad: cfg.entidad, valor: cfg.valor, etiqueta: cfg.etiqueta };
    ['mix', 'grupo', 'periodo', 'grupo_valor'].forEach((k) => { if (cfg[k]) b[k] = cfg[k]; });
    return b;
  },

  async calcularMatriz(ds, btn) {
    btn.disabled = true;
    clear(this.salidaMatriz).appendChild(note(t('common.loading'), 'info'));
    try {
      const r = await api.post('/api/portafolio/contribucion', this.cuerpoMatriz(ds));
      this.matrizLista = true;
      audio.beep('done');
      this.pintarMatriz(r, ds, btn);
    } catch (err) { clear(this.salidaMatriz); fail(err); } finally { btn.disabled = false; }
  },

  pintarMatriz(r, ds, btn) {
    const out = clear(this.salidaMatriz);
    if (r.grupos_disponibles) {
      out.appendChild(el('div', { class: 'card' }, campo(t('port.area'),
        sel([['', t('port.todas')], ...r.grupos_disponibles.map((g) => [g, g])], cfg.grupo_valor,
          (v) => { cfg.grupo_valor = v; this.calcularMatriz(ds, btn); }))));
    }
    const k = Object.fromEntries(r.kpis.map((x) => [x.kpi, x]));
    out.appendChild(el('div', { class: 'grid grid-3' },
      stat(t('port.ventas'), num(Math.round(k.ventas_total.valor)), k.ventas_total.texto),
      k.combinaciones ? stat(t('port.combinaciones'), pct(k.combinaciones.valor, 0), k.combinaciones.texto) : null,
      stat(t('port.concentracion'), pct(k.concentracion_top.valor, 0), k.concentracion_top.texto)));
    if (r.aviso) out.appendChild(note(r.aviso, 'warn'));
    const items = r.entidades.map((e) => ({
      label: e.entidad, valor: pct(e.contribucion, 1), contribucion: e.contribucion, accion: e.accion,
      x: r.eje_x === 'mix' ? e.indice_mix : (e.crecimiento ?? 0),
      tooltip: `${e.entidad} · ${pct(e.contribucion, 1)} · ${e.etapa_mix || ''} ${e.siguiente_motor || ''}`.trim(),
    }));
    const u = r.umbrales;
    out.appendChild(el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h2', { text: t('port.burbujas') })),
      charts.bubbles(items, { alta: u.alta, media: u.media, zonas: r.zonas_x, ejeX: r.eje_x,
        niveles: [`${t('port.baja')} (<${pct(u.media, 0)})`, `${t('port.media')} (${pct(u.media, 0)}–${pct(u.alta, 0)})`,
          `${t('port.alta')} (>${pct(u.alta, 0)})`] })));
    out.appendChild(el('div', { class: 'grid grid-3' }, ...r.lectura.map((x) => el('div', { class: 'card port-lectura' },
      el('h3', { text: x.bloque }), el('p', {}, el('strong', { text: x.titulo })), el('p', { text: x.texto })))));
    const motor = Object.fromEntries(r.entidades.map((e) => [e.entidad, e.siguiente_motor]));
    out.appendChild(el('div', { class: 'card' }, el('div', { class: 'port-acciones' },
      ...Object.entries(r.acciones).map(([a, ents]) => el('div', { class: `port-accion ${a}` },
        el('h3', { text: r.preguntas[a] }),
        el('ul', {}, ...ents.map((e) => el('li', { text: motor[e] ? `${e} · ${motor[e]}` : e }))))))));
    out.appendChild(el('div', { class: 'card' }, table([
      { key: 'entidad', label: t('port.entidad') },
      { key: 'contribucion', label: t('port.contribucion'), align: 'right', format: (v) => pct(v, 1) },
      { key: 'accion', label: t('port.accion'), render: (v) => badge(v, ACCION_KIND[v]) },
      { key: r.eje_x === 'mix' ? 'etapa_mix' : 'crecimiento', label: r.eje_x === 'mix' ? t('port.etapa') : t('port.crecimiento'),
        format: (v) => (typeof v === 'number' ? pct(v, 1) : v ?? '') },
      { key: 'siguiente_motor', label: t('port.motor'), format: (v) => v ?? '' },
    ], r.entidades, { compact: true })));
  },

  async descargarPowerBI(ds, btn) {
    btn.disabled = true;
    try {
      // Va lo que ya se calculó en pantalla: la matriz, el mercado o los dos.
      const body = {};
      if (this.matrizLista) {
        body.contribucion = this.cuerpoMatriz(ds);
        delete body.contribucion.grupo_valor;
      }
      if (this.ultimoMercado) body.mercado = this.ultimoMercado;
      if (!body.contribucion && !body.mercado) { clear(this.pbiHost).appendChild(note(t('port.nada_que_exportar'), 'warn')); return; }
      const r = await api.post('/api/portafolio/powerbi', body);
      clear(this.pbiHost).appendChild(el('a', { class: 'btn btn-primary mt-1', href: api.withWorkspace(r.download_url), download: '' },
        icon('download', 15), t('common.download')));
    } catch (err) { fail(err); } finally { btn.disabled = false; }
  },

  /* ── agente de mercado ──────────────────────────────────────────────── */
  formMercado(s) {
    const estudios = sel([['', t('port.sin_estudios')], ...s.datasets.map((d) => [d.id, d.name])], ctx.estudios,
      (v) => { ctx.estudios = v; });
    const forma = sel(['rapida', 'media', 'lenta'].map((f) => [f, t(`port.forma_${f}`)]), ctx.forma, (v) => { ctx.forma = v; });
    const proponer = el('button', { class: 'btn' }, icon('ai', 15), t('port.proponer'));
    proponer.onclick = () => this.proponer(proponer);
    const analizar = el('button', { class: 'btn btn-primary' }, icon('results', 15), t('port.analizar'));
    analizar.onclick = () => this.analizar(analizar);
    const plantilla = el('button', { class: 'btn' }, icon('download', 15), t('port.plantilla'));
    plantilla.onclick = () => {
      const q = new URLSearchParams({ paises: ctx.paises, segmentos: ctx.segmentos });
      window.location.href = api.withWorkspace(`/api/mercado/plantilla?${q}`);
    };
    return el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('div', {}, el('h2', { text: t('port.mercado') }),
        el('div', { class: 'card-sub', text: t('port.mercado_sub') }))),
      el('div', { class: 'grid grid-3' },
        campo(t('port.area'), entrada('area_terapeutica')), campo(t('port.molecula'), entrada('molecula')),
        campo(t('port.enfermedad'), entrada('enfermedad')), campo(t('port.presentacion'), entrada('presentacion')),
        campo(t('port.paises'), entrada('paises')), campo(t('port.segmentos'), entrada('segmentos')),
        campo(t('port.estudios'), estudios), campo(t('port.pico'), entrada('pico', 'number')),
        campo(t('port.meses_pico'), entrada('meses', 'number')), campo(t('port.horizonte'), entrada('horizonte', 'number')),
        campo(t('port.forma'), forma)),
      el('div', { class: 'row' }, plantilla, proponer, analizar));
  },

  async proponer(btn) {
    btn.disabled = true;
    const out = clear(this.salidaMercado);
    out.appendChild(note(t('common.loading'), 'info'));
    try {
      propuesta = await api.post('/api/mercado/proponer', { ...ctx, paises: lista(ctx.paises), segmentos: lista(ctx.segmentos) });
      clear(out);
      propuesta.avisos.forEach((a) => out.appendChild(note(a, 'warn')));
      out.appendChild(el('div', { class: 'card' },
        el('div', { class: 'card-head' }, el('h2', { text: t('port.casuistica') })),
        table([{ key: 'tema', label: t('port.tema') }, { key: 'lectura', label: t('port.lectura') }], propuesta.casuistica, { compact: true })));
      out.appendChild(this.tablaSupuestos(propuesta.supuestos));
    } catch (err) { clear(out); fail(err); } finally { btn.disabled = false; }
  },

  tablaSupuestos(filas) {
    return el('div', { class: 'card' }, el('div', { class: 'card-head' }, el('h2', { text: t('port.supuestos') })),
      table([
        { key: 'pais', label: t('port.pais') }, { key: 'segmento', label: t('port.segmento') },
        { key: 'parametro', label: t('port.parametro') },
        { key: 'valor', label: t('port.valor_central'), align: 'right', format: (v) => num(v, v < 1 ? 3 : 0) },
        { key: 'minimo', label: 'min', align: 'right', format: (v) => num(v, v < 1 ? 3 : 0) },
        { key: 'maximo', label: 'max', align: 'right', format: (v) => num(v, v < 1 ? 3 : 0) },
        { key: 'origen', label: t('port.origen'), render: (v) => badge(v, v.startsWith('IA') ? 'warn' : 'ok') },
        { key: 'fuente', label: t('port.fuente') },
      ], filas, { compact: true, maxHeight: '320px' }));
  },

  async analizar(btn) {
    btn.disabled = true;
    const out = clear(this.salidaMercado);
    out.appendChild(note(t('common.loading'), 'info'));
    const body = { n_sim: 2000, inicio: null,
      lanzamiento: ctx.pico > 0 ? { pico: ctx.pico / 100, meses_al_pico: ctx.meses, horizonte: ctx.horizonte, forma: ctx.forma } : null };
    if (propuesta) body.supuestos = propuesta.supuestos;
    if (ctx.estudios) body.estudios_dataset_id = ctx.estudios;
    try {
      const r = await api.post('/api/mercado/analizar', body);
      this.ultimoMercado = body;
      audio.beep('done');
      this.pintarMercado(r);
    } catch (err) { clear(out); fail(err); } finally { btn.disabled = false; }
  },

  pintarMercado(r) {
    const out = clear(this.salidaMercado);
    out.appendChild(el('div', { class: 'card' }, el('div', { class: 'proy-veredicto' },
      badge(`${t('port.evidencia')}: ${r.evidencia.nivel}`, EVIDENCIA_KIND[r.evidencia.nivel]),
      el('p', { text: r.recomendaciones.join(' ') }))));
    r.avisos.forEach((a) => out.appendChild(note(a, 'warn')));
    const porPais = r.lecturas.map((l) => ({ label: l.pais, en_clase: l.en_clase, latente: l.latente }));
    out.appendChild(el('div', { class: 'grid grid-2' },
      el('div', { class: 'card' }, el('div', { class: 'card-head' }, el('h2', { text: t('port.actual_latente') })),
        charts.bars(porPais, { valueKey: 'en_clase', second: 'latente', fmtY: compacto }),
        el('p', { class: 'hint', text: t('port.actual_latente_hint') })),
      el('div', { class: 'card' }, el('div', { class: 'card-head' }, el('h2', { text: t('port.tornado') })),
        charts.hbars(r.sensibilidad.map((x) => ({ label: x.parametro, value: x.oscilacion })), { fmt: compacto }))));
    out.appendChild(el('div', { class: 'card' }, table([
      { key: 'pais', label: t('port.pais') },
      { key: 'accion', label: t('port.accion'), render: (v) => badge(v, ACCION_KIND[v]) },
      { key: 'lectura', label: t('port.lectura') },
    ], r.lecturas, { compact: true })));
    if (r.lanzamiento) {
      const tot = r.lanzamiento.filter((x) => x.pais === 'Total');
      const serie = (k) => tot.map((x) => [x.mes, x[k]]);
      const k = tot[0] && 'valor_p50' in tot[0] ? 'valor' : 'unidades';
      out.appendChild(el('div', { class: 'card' },
        el('div', { class: 'card-head' }, el('div', {}, el('h2', { text: t('port.lanzamiento') }),
          el('div', { class: 'card-sub', text: r.lanzamiento_nota }))),
        charts.line([serie(`${k}_p50`), serie(`${k}_p10`), serie(`${k}_p90`)], {
          width: 900, height: 280, fmtX: (v) => String(Math.round(v)), fmtY: compacto,
          labels: ['P50', 'P10 – P90'] })));
    }
    out.appendChild(this.tablaSupuestos(r.supuestos));
    out.appendChild(el('p', { class: 'hint', text: r.nota }));
  },
};
