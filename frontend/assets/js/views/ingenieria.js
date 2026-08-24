/**
 * Vista de ingeniería de datos: claves, tiempo, cruces y contrato.
 *
 * Las cuatro preguntas que hay que contestar antes de modelar y que ninguna
 * pantalla contestaba: qué identifica una fila, si la serie de tiempo está
 * completa, qué se puede cruzar con qué sin multiplicar filas, y cómo se lleva
 * la tabla a un servidor SQL con sus verificaciones.
 */
import * as api from '../api.js';
import { t, num, dec } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import { el, clear, table, badge, note, emptyState, stat, fail, toast, icon } from '../ui.js';
import { bars } from '../charts.js';

let nav = null;

const KIND_RIESGO = { alto: 'bad', medio: 'warn', bajo: 'ok' };

/** Copia al portapapeles con respaldo para contextos sin permiso (escritorio). */
async function copiar(texto) {
  try {
    await navigator.clipboard.writeText(texto);
  } catch {
    const ta = el('textarea', { style: 'position:fixed;opacity:0' });
    ta.value = texto;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } finally { ta.remove(); }
  }
  toast(t('common.copied'), 'ok');
}

/** Bloque de código con botón de copiar y de bajar a archivo. */
function codigo(texto, archivo) {
  const copiarBtn = el('button', { class: 'btn btn-sm' }, t('common.copy'));
  copiarBtn.onclick = () => copiar(texto);
  const url = URL.createObjectURL(new Blob([texto], { type: 'text/plain;charset=utf-8' }));
  return el('div', {},
    el('div', { class: 'row mb-1' }, copiarBtn,
      el('a', { class: 'btn btn-sm', href: url, download: archivo },
        icon('download', 14), t('common.download'))),
    el('pre', { class: 'code', text: texto }));
}

/* ── claves ───────────────────────────────────────────────────────────────── */
function tarjetaClaves(k) {
  const cuerpo = el('div');
  if (k.sin_clave) {
    cuerpo.appendChild(note(t('ing.keys_none'), 'warn'));
  }
  const filas = [
    ...k.pk_simple.map((x) => ({ ...x, tipo: t('ing.keys_pk') })),
    ...k.pk_compuesta.map((x) => ({ columna: x.columnas.join(' + '), confianza: x.confianza,
      por_que: x.por_que, tipo: t('ing.keys_composite') })),
    ...k.pk_candidata.map((x) => ({ ...x, tipo: t('ing.keys_candidate') })),
    ...k.fk_candidatas.map((x) => ({ columna: x.columna, confianza: '',
      por_que: `${num(x.distintos)} ${t('ing.keys_distinct')}`, tipo: t('ing.keys_fk') })),
  ];
  if (filas.length) {
    cuerpo.appendChild(table([
      { key: 'tipo', label: t('common.type'),
        render: (v) => badge(v, v === t('ing.keys_pk') ? 'ok' : '') },
      { key: 'columna', label: t('common.column'), mono: true },
      { key: 'confianza', label: t('ing.keys_confidence') },
      { key: 'por_que', label: t('ing.why') },
    ], filas));
  } else {
    cuerpo.appendChild(emptyState(t('common.empty')));
  }
  if (k.constantes.length) {
    cuerpo.appendChild(el('div', { class: 'small muted mt-1' },
      `${t('ing.keys_constants')}: `, el('span', { class: 'mono', text: k.constantes.join(', ') })));
  }
  if (k.duplicados_exactos) {
    cuerpo.appendChild(note(`${t('ing.keys_duplicates')}: ${num(k.duplicados_exactos)}`, 'warn'));
  }
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('ing.keys_title') }),
        el('div', { class: 'card-sub', text: t('ing.keys_note') }))),
    cuerpo);
}

/* ── tiempo ───────────────────────────────────────────────────────────────── */
function tarjetaTiempo(ti, columnas, alCambiar) {
  const cuerpo = el('div');
  if (!ti) {
    cuerpo.appendChild(emptyState(t('ing.time_none')));
    return el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h2', { text: t('ing.time_title') })), cuerpo);
  }
  const cobertura = ti.cobertura_pct >= 99 ? 'ok' : (ti.cobertura_pct >= 90 ? 'warn' : 'bad');
  cuerpo.appendChild(el('div', { class: 'grid grid-4 mb-2' },
    stat(t('ing.time_grain'), t(`ing.grain_${ti.granularidad}`),
      `${ti.desde.slice(0, 10)} → ${ti.hasta.slice(0, 10)}`),
    stat(t('ing.time_coverage'), `${dec(ti.cobertura_pct, 1)}%`,
      `${num(ti.periodos_con_datos)} / ${num(ti.periodos_rango)} ${t(`ing.unit_${ti.unidad}`)}`,
      cobertura),
    stat(t('ing.time_gaps'), num(ti.periodos_faltantes), t(`ing.unit_${ti.unidad}`),
      ti.periodos_faltantes ? 'warn' : 'ok'),
    stat(t('ing.time_freshness'), `${num(ti.frescura_dias)} d`,
      ti.tendencia ? t(`ing.trend_${ti.tendencia}`) : '',
      ti.frescura_dias > 90 ? 'warn' : 'ok')));

  if (columnas.length > 1) {
    const sel = el('select', { style: 'max-width:280px' },
      ...columnas.map((c) => el('option', { value: c, text: c, selected: c === ti.columna })));
    sel.onchange = () => alCambiar(sel.value);
    cuerpo.appendChild(el('div', { class: 'field' },
      el('label', { text: t('ing.time_column') }), sel));
  }
  if (ti.fechas_futuras) {
    cuerpo.appendChild(note(`${t('ing.time_future')}: ${num(ti.fechas_futuras)}`, 'warn'));
  }
  if (ti.huecos.length) {
    cuerpo.appendChild(el('div', { class: 'small mt-1' },
      `${t('ing.time_gaps_list')}: `,
      el('span', { class: 'mono', text: ti.huecos.join(' · ') })));
  }
  if (ti.serie_mensual.length > 1) {
    cuerpo.appendChild(bars(ti.serie_mensual.map((s) => ({ label: s.mes, value: s.filas })),
      { title: t('ing.time_series'), fmtY: (v) => num(Math.round(v)) }));
  }
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('ing.time_title') }),
        el('div', { class: 'card-sub', text: t('ing.time_note') }))),
    cuerpo);
}

/* ── cruces ───────────────────────────────────────────────────────────────── */
function tarjetaCruces() {
  const cuerpo = el('div');
  const btn = el('button', { class: 'btn' }, t('ing.joins_scan'));
  btn.onclick = async () => {
    btn.disabled = true;
    clear(cuerpo).appendChild(el('div', { class: 'row' },
      el('span', { class: 'spinner' }), el('span', { text: t('common.loading') })));
    try {
      const r = await api.post('/api/ingenieria/cruces', {});
      clear(cuerpo);
      if (r.nota) { cuerpo.appendChild(note(r.nota, 'warn')); return; }
      if (!r.sugerencias.length) { cuerpo.appendChild(emptyState(t('ing.joins_empty'))); return; }
      cuerpo.appendChild(table([
        { key: 'izquierda', label: t('ing.joins_left') },
        { key: 'derecha', label: t('ing.joins_right') },
        { key: 'columna', label: t('common.column'), mono: true },
        { key: 'cardinalidad', label: t('ing.joins_cardinality'),
          render: (v, row) => badge(v, KIND_RIESGO[row.riesgo] || '') },
        { key: 'solape_pct', label: t('ing.joins_overlap'), align: 'right',
          format: (v) => `${dec(v, 1)}%` },
        { key: 'aviso', label: t('ing.joins_warning') },
      ], r.sugerencias));
      const conSql = r.sugerencias[0];
      if (conSql) cuerpo.appendChild(codigo(conSql.sql, 'cruce.sql'));
    } catch (err) { clear(cuerpo); fail(err); } finally { btn.disabled = false; }
  };
  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('ing.joins_title') }),
        el('div', { class: 'card-sub', text: t('ing.joins_note') })), btn),
    cuerpo);
}

/* ── contrato ─────────────────────────────────────────────────────────────── */
function tarjetaContrato(co, dialectos, alCambiar) {
  const sel = el('select', { style: 'max-width:240px' },
    ...dialectos.map((d) => el('option', { value: d.id, text: d.label, selected: d.id === co.dialecto })));
  sel.onchange = () => alCambiar(sel.value);

  const dic = table([
    { key: 'columna', label: t('common.column'), mono: true },
    { key: 'tipo', label: t('ing.contract_type'), mono: true },
    { key: 'rol', label: t('ing.contract_role'), render: (v) => badge(v) },
    { key: 'obligatoria', label: t('ing.contract_required'),
      render: (v) => badge(v ? t('common.yes') : t('common.no'), v ? 'ok' : '') },
    { key: 'nulos_pct', label: t('ing.contract_nulls'), align: 'right',
      format: (v) => `${dec(v || 0, 1)}%` },
    { key: 'distintos', label: t('ing.contract_distinct'), align: 'right', format: (v) => num(v || 0) },
    { key: 'ejemplo', label: t('ing.contract_example') },
  ], co.diccionario, { maxHeight: '420px' });

  const checks = el('div');
  co.verificaciones.forEach((v) => {
    checks.appendChild(el('details', { class: 'mt-1' },
      el('summary', { style: 'cursor:pointer;font-weight:600', text: v.nombre }),
      el('div', { class: 'small muted mt-1', text: v.por_que }),
      el('pre', { class: 'code mt-1', text: v.sql })));
  });

  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h2', { text: t('ing.contract_title') }),
        el('div', { class: 'card-sub', text: t('ing.contract_note') })),
      el('div', { class: 'field mb-0' }, el('label', { text: t('ing.contract_dialect') }), sel)),
    el('h3', { class: 'mt-2', text: t('ing.contract_dictionary') }), dic,
    el('h3', { class: 'mt-2', text: t('ing.contract_ddl') }),
    codigo(co.ddl, `${co.tabla}.sql`),
    el('h3', { class: 'mt-2', text: t('ing.contract_checks') }),
    el('div', { class: 'small muted', text: t('ing.contract_checks_note') }), checks,
    el('h3', { class: 'mt-2', text: t('ing.contract_dbt') }),
    codigo(co.dbt, `stg_${co.tabla}.yml`));
}

export default {
  mount(host, { go }) { nav = go; this.host = host; },

  async refresh() {
    const host = this.host;
    const s = store.get();
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('ing.title') }),
      el('p', { class: 'page-lead', text: t('ing.lead') })));

    if (!s.datasetId) {
      host.appendChild(emptyState(t('errors.no_dataset')));
      host.appendChild(el('button', { class: 'btn btn-primary mt-2', onClick: () => nav('data') },
        t('nav.data')));
      return;
    }

    const cuerpo = el('div');
    host.appendChild(cuerpo);
    const cargando = () => clear(cuerpo).appendChild(el('div', { class: 'card' },
      el('div', { class: 'row' }, el('span', { class: 'spinner' }),
        el('span', { text: t('common.loading') }))));

    let dialectos = [];
    let dialecto = localStorage.getItem('mv.dialecto') || 'sqlserver';
    let columnaTiempo = null;

    const pintar = async (conSonido) => {
      cargando();
      try {
        if (!dialectos.length) {
          dialectos = (await api.get('/api/ingenieria/dialectos')).dialectos;
        }
        const q = new URLSearchParams({ dialecto });
        if (columnaTiempo) q.set('columna_tiempo', columnaTiempo);
        const r = await api.get(`/api/ingenieria/${s.datasetId}?${q}`);
        clear(cuerpo);
        cuerpo.appendChild(el('div', { class: 'grid grid-4 mb-2' },
          stat(t('common.rows'), num(r.filas)),
          stat(t('common.columns'), num(r.columnas)),
          stat(t('ing.keys_title'),
            r.claves.sin_clave ? t('ing.keys_no') : t('ing.keys_yes'),
            r.claves.pk_simple[0]?.columna
              || r.claves.pk_compuesta[0]?.columnas.join(' + ') || '',
            r.claves.sin_clave ? 'warn' : 'ok'),
          stat(t('ing.quality'), `${dec(r.calidad?.score ?? 0, 0)}/100`, '',
            (r.calidad?.score ?? 0) >= 80 ? 'ok' : 'warn')));

        const fechas = (store.dataset()?.columns || [])
          .filter((c) => String(c.arrow_type || '').toLowerCase().includes('timestamp')
            || String(c.arrow_type || '').toLowerCase().includes('date'))
          .map((c) => c.name);

        cuerpo.appendChild(tarjetaClaves(r.claves));
        cuerpo.appendChild(tarjetaTiempo(r.tiempo, fechas, (c) => {
          columnaTiempo = c; pintar(false);
        }));
        cuerpo.appendChild(tarjetaCruces());
        cuerpo.appendChild(tarjetaContrato(r.contrato, dialectos, (d) => {
          dialecto = d; localStorage.setItem('mv.dialecto', d); pintar(false);
        }));
        if (conSonido) audio.beep('success');
      } catch (err) { clear(cuerpo); fail(err); }
    };

    await pintar(true);
  },
};
