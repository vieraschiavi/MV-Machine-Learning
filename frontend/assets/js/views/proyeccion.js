/**
 * Proyecciones: cuánto va a pasar el período que viene, y cuánto creerle.
 *
 * La pantalla muestra tres cosas juntas y a propósito: la línea proyectada,
 * la tabla del backtest que dice cuánto erró cada método en el pasado, y el
 * veredicto en castellano. Una proyección sin su medición es una opinión con
 * gráfico, y esa es justo la forma en que un tablero hace tomar una mala
 * decisión con cara de dato.
 */
import * as api from '../api.js';
import { t, num } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import * as charts from '../charts.js';
import { el, clear, note, emptyState, fail, toast, icon, table } from '../ui.js';

let nav = null;
// El dataset NO se guarda acá: es el activo de la aplicación (store.datasetId).
// Guardarlo en la pestaña la dejaba clavada en el primero que vio, y el
// archivo o la consulta SQL que se cargaba después no le llegaba nunca.
const elegido = { tiempo: null, valor: null, grano: 'month',
  agregacion: 'sum', horizonte: 6 };

const SEMAFORO = { ok: 'ok', revisar: 'warn', alerta: 'bad' };

function sel(opciones, valor, onchange) {
  const s = el('select', {}, ...opciones.map(([v, txt]) => el('option', {
    value: v, text: txt, selected: v === valor })));
  s.onchange = onchange;
  return s;
}

export default {
  mount(host, { go }) { nav = go; this.host = host; },

  async refresh() {
    const host = this.host;
    const s = store.get();
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('proy.title') }),
      el('p', { class: 'page-lead', text: t('proy.lead') })));

    if (!s.datasets.length) { host.appendChild(emptyState(t('errors.no_dataset'))); return; }

    const dsSel = el('select', {}, ...s.datasets.map((d) => el('option', {
      value: d.id, text: d.name, selected: d.id === s.datasetId })));
    const campos = el('div', { class: 'grid grid-3' });
    const salida = el('div', { class: 'proy-salida' });
    const self = this;
    const btn = el('button', { class: 'btn btn-primary' }, icon('results', 15), t('proy.calcular'));

    const cargarColumnas = async () => {
      clear(campos);
      clear(salida);
      let c;
      try { c = await api.get(`/api/proyeccion/columnas/${dsSel.value}`); }
      catch (err) { fail(err); return; }

      // Sin fecha o sin número no hay serie: se avisa Y se apaga el botón.
      // Antes sólo se avisaba, el botón quedaba vivo, y apretarlo mandaba
      // `null` al servidor — el usuario veía el 422 crudo de pydantic.
      if (!c.fechas.length || !c.numericas.length) {
        salida.appendChild(note(t('proy.sin_fecha'), 'warn'));
        elegido.tiempo = null;
        elegido.valor = null;
        btn.disabled = true;
        return;
      }
      btn.disabled = false;
      elegido.tiempo = c.fechas.includes(elegido.tiempo) ? elegido.tiempo : c.fechas[0];
      elegido.valor = c.numericas.includes(elegido.valor) ? elegido.valor : c.numericas[0];

      const granos = c.granos.map((g) => [g, t(`proy.grano_${g}`)]);
      const aggs = c.agregaciones.map((a) => [a, t(`proy.agg_${a}`)]);
      campos.appendChild(el('div', { class: 'field' }, el('label', { text: t('proy.columna_tiempo') }),
        sel(c.fechas.map((f) => [f, f]), elegido.tiempo, (e) => { elegido.tiempo = e.target.value; })));
      campos.appendChild(el('div', { class: 'field' }, el('label', { text: t('proy.columna_valor') }),
        sel(c.numericas.map((f) => [f, f]), elegido.valor, (e) => { elegido.valor = e.target.value; })));
      campos.appendChild(el('div', { class: 'field' }, el('label', { text: t('proy.grano') }),
        sel(granos, elegido.grano, (e) => { elegido.grano = e.target.value; })));
      campos.appendChild(el('div', { class: 'field' }, el('label', { text: t('proy.agregacion') }),
        sel(aggs, elegido.agregacion, (e) => { elegido.agregacion = e.target.value; })));
      const h = el('input', { type: 'number', min: '1', max: '120', value: String(elegido.horizonte) });
      h.onchange = () => { elegido.horizonte = Number(h.value) || 6; };
      campos.appendChild(el('div', { class: 'field' }, el('label', { text: t('proy.horizonte') }), h));
    };

    dsSel.onchange = () => { store.elegirDataset(dsSel.value); cargarColumnas(); };

    btn.onclick = async () => {
      if (!elegido.tiempo || !elegido.valor) return;
      btn.disabled = true;
      clear(salida).appendChild(note(t('common.loading'), 'info'));
      try {
        const r = await api.post('/api/proyeccion', {
          dataset_id: dsSel.value, columna_tiempo: elegido.tiempo,
          columna_valor: elegido.valor, horizonte: elegido.horizonte,
          grano: elegido.grano, agregacion: elegido.agregacion,
        });
        audio.beep('done');
        self.pintar(salida, r);
      } catch (err) { clear(salida); fail(err); }
      finally { btn.disabled = false; }
    };

    host.appendChild(el('div', { class: 'card' },
      el('div', { class: 'field' }, el('label', { text: t('nav.data') }), dsSel),
      campos, el('div', { class: 'row' }, btn)));
    host.appendChild(salida);
    await cargarColumnas();
  },

  pintar(salida, r) {
    clear(salida);

    /* ── veredicto primero: es lo que decide si mirar el resto ─────────── */
    salida.appendChild(el('div', { class: 'card' },
      el('div', { class: 'proy-veredicto' },
        el('span', { class: `chip chip-${SEMAFORO[r.veredicto.nivel] || 'info'}`,
          text: t(`proy.nivel_${r.veredicto.nivel}`) }),
        el('p', { text: r.veredicto.texto }))));

    /* ── el gráfico: historia + proyección con su banda ────────────────── */
    const hist = r.serie.valores.map((v, i) => [i, v]);
    const base = r.serie.valores.length - 1;
    const linea = [[base, r.serie.valores[base]],
      ...r.proyeccion.map((p, i) => [base + i + 1, p.valor])];
    const inf = [[base, r.serie.valores[base]],
      ...r.proyeccion.map((p, i) => [base + i + 1, p.inferior])];
    const sup = [[base, r.serie.valores[base]],
      ...r.proyeccion.map((p, i) => [base + i + 1, p.superior])];
    const etiquetas = [...r.serie.periodos, ...r.proyeccion.map((p) => p.periodo)];

    salida.appendChild(el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h2', { text: t('proy.grafico') })),
      charts.line([hist, linea, inf, sup], {
        width: 900, height: 300,
        fmtX: (v) => etiquetas[Math.round(v)] || '',
        fmtY: (v) => num(Math.round(v)),
        labels: [t('proy.historico'), t('proy.proyectado')],
      })));

    /* ── la tabla: lo que se copia al Excel ────────────────────────────── */
    salida.appendChild(el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h2', { text: t('proy.tabla') })),
      table([
        { key: 'periodo', label: t('proy.periodo') },
        { key: 'valor', label: t('proy.valor'), align: 'right', format: (v) => num(Math.round(v)) },
        { key: 'inferior', label: t('proy.inferior'), align: 'right', format: (v) => num(Math.round(v)) },
        { key: 'superior', label: t('proy.superior'), align: 'right', format: (v) => num(Math.round(v)) },
      ], r.proyeccion)));

    /* ── el backtest: por qué creerle (o no) ───────────────────────────── */
    const filas = r.backtest.map((f) => ({ ...f,
      elegido: r.modelos_combinados.includes(f.modelo) ? '✓' : '' }));
    salida.appendChild(el('div', { class: 'card' },
      el('div', { class: 'card-head' },
        el('div', {}, el('h2', { text: t('proy.backtest') }),
          el('div', { class: 'card-sub',
            text: t('proy.backtest_sub').replace('{n}', String(r.origenes_evaluados)) }))),
      table([
        { key: 'elegido', label: '' },
        { key: 'modelo', label: t('proy.modelo') },
        { key: 'MASE', label: 'MASE', align: 'right', format: (v) => v.toFixed(3) },
        { key: 'sMAPE', label: 'sMAPE %', align: 'right', format: (v) => v.toFixed(1) },
        { key: 'origenes', label: t('proy.origenes'), align: 'right' },
      ], filas),
      el('p', { class: 'hint mt-1', text: t('proy.mase_hint') })));
  },
};
