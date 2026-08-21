/**
 * El monitor del negocio: cuántos clientes, cuánto se descargó y cuánta plata
 * entró de verdad.
 *
 * No hay base de datos ni servicio de analítica: las dos únicas fuentes son las
 * que ya existen y no cuestan nada.
 *
 *   · **Plata y clientes** → la API de MercadoPago. Se pide el neto acreditado
 *     (`net_received_amount`), que es lo que realmente queda después de la
 *     comisión, no el precio de lista.
 *   · **Descargas** → la API pública de GitHub. Cada archivo publicado en un
 *     release lleva su propio contador.
 *
 * Nada de esto se guarda acá: se consulta en el momento. Si mañana se cambia de
 * plataforma de cobro, el historial sigue estando en MercadoPago.
 *
 * Variables de entorno:
 *   PANEL_CLAVE       contraseña para entrar. Sin ella el panel queda cerrado.
 *   MP_ACCESS_TOKEN   credencial de MercadoPago (la misma del cobro)
 *   GITHUB_TOKEN      opcional: sube el límite de consultas a GitHub
 *   REPO              opcional: "usuario/repositorio" de donde salen las descargas
 */
import { claveValida } from './_firmar.js';

const REPO = process.env.REPO || 'vieraschiavi/MV-Machine-Learning';
const PAGINA = 100;          // máximo que acepta la búsqueda de MercadoPago
const TOPE = 1000;           // hasta acá se pagina; más que eso pide otra herramienta

const numero = (v) => (typeof v === 'number' && isFinite(v) ? v : 0);

/** Trae los pagos de la cuenta, del más nuevo al más viejo. */
async function traerPagos(token) {
  const pagos = [];
  for (let offset = 0; offset < TOPE; offset += PAGINA) {
    const url = `https://api.mercadopago.com/v1/payments/search`
      + `?sort=date_created&criteria=desc&limit=${PAGINA}&offset=${offset}`;
    const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!r.ok) {
      const detalle = await r.text();
      throw new Error(`MercadoPago respondió ${r.status}: ${detalle.slice(0, 200)}`);
    }
    const datos = await r.json();
    const lote = datos.results || [];
    pagos.push(...lote);
    if (lote.length < PAGINA) break;
  }
  return pagos;
}

export function resumirVentas(pagos) {
  const correos = new Set();
  const porPlan = {};
  const porMes = {};
  let bruto = 0, neto = 0, aprobados = 0, pendientes = 0, rechazados = 0, devuelto = 0;
  let moneda = 'USD';

  for (const p of pagos) {
    if (p.status === 'pending' || p.status === 'in_process') { pendientes++; continue; }
    if (p.status === 'rejected' || p.status === 'cancelled') { rechazados++; continue; }
    if (p.status !== 'approved' && p.status !== 'refunded') continue;

    const monto = numero(p.transaction_amount);
    // El neto es lo que MercadoPago deposita: precio menos su comisión. Si por
    // algún motivo no viene, se cae al bruto para no inventar un número.
    const acreditado = numero(p.transaction_details?.net_received_amount) || monto;
    const reintegro = numero(p.transaction_amount_refunded);
    const plan = String(p.external_reference || 'sin-plan').split(':')[0];
    const mes = String(p.date_approved || p.date_created || '').slice(0, 7);
    if (p.currency_id) moneda = p.currency_id;

    if (p.status === 'approved') {
      aprobados++;
      bruto += monto;
      neto += acreditado - reintegro;
      if (p.payer?.email) correos.add(p.payer.email.toLowerCase());
      porPlan[plan] = porPlan[plan] || { ventas: 0, bruto: 0, neto: 0 };
      porPlan[plan].ventas++;
      porPlan[plan].bruto += monto;
      porPlan[plan].neto += acreditado - reintegro;
      if (mes) {
        porMes[mes] = porMes[mes] || { ventas: 0, bruto: 0, neto: 0 };
        porMes[mes].ventas++;
        porMes[mes].bruto += monto;
        porMes[mes].neto += acreditado - reintegro;
      }
    }
    devuelto += reintegro;
  }

  const ultimos = pagos.slice(0, 12).map((p) => ({
    fecha: p.date_approved || p.date_created,
    plan: String(p.external_reference || '—').split(':')[0],
    correo: p.payer?.email || '—',
    monto: numero(p.transaction_amount),
    estado: p.status,
    medio: p.payment_method_id || '—',
  }));

  return {
    disponible: true, moneda,
    clientes: correos.size, ventas: aprobados, pendientes, rechazados,
    bruto: +bruto.toFixed(2), neto: +neto.toFixed(2),
    comision: +(bruto - neto).toFixed(2),
    devuelto: +devuelto.toFixed(2),
    porPlan, porMes, ultimos,
  };
}

async function traerDescargas() {
  const cab = { Accept: 'application/vnd.github+json' };
  if (process.env.GITHUB_TOKEN) cab.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  const r = await fetch(`https://api.github.com/repos/${REPO}/releases?per_page=100`, {
    headers: cab,
  });
  if (!r.ok) throw new Error(`GitHub respondió ${r.status}`);
  const releases = await r.json();

  let total = 0;
  const archivos = [];
  for (const rel of releases) {
    for (const a of rel.assets || []) {
      const bajadas = numero(a.download_count);
      total += bajadas;
      archivos.push({
        archivo: a.name,
        release: rel.tag_name,
        borrador: !!rel.draft,
        descargas: bajadas,
        publicado: rel.published_at || rel.created_at,
      });
    }
  }
  archivos.sort((x, y) => y.descargas - x.descargas);
  const demo = archivos.filter((a) => /demo/i.test(a.archivo))
    .reduce((s, a) => s + a.descargas, 0);
  return { disponible: true, total, demo, owner: total - demo, archivos };
}

export default async function handler(req, res) {
  const esperada = process.env.PANEL_CLAVE;
  if (!esperada) {
    return res.status(503).json({
      error: 'El panel todavía no está habilitado.',
      detalle: 'Falta la variable de entorno PANEL_CLAVE en el servidor.',
    });
  }
  const dada = req.headers['x-mv-panel'] || req.query?.clave;
  if (!claveValida(dada, esperada)) {
    // Sin pistas: el mismo mensaje si la clave falta o si está mal.
    return res.status(401).json({ error: 'Clave incorrecta.' });
  }

  // Las dos fuentes se consultan en paralelo y cada una falla por su cuenta: que
  // GitHub esté caído no debería dejarte sin ver la facturación.
  const [ventas, descargas] = await Promise.all([
    (async () => {
      const token = process.env.MP_ACCESS_TOKEN;
      if (!token) return { disponible: false, motivo: 'Falta MP_ACCESS_TOKEN.' };
      try { return resumirVentas(await traerPagos(token)); }
      catch (e) { return { disponible: false, motivo: e.message }; }
    })(),
    (async () => {
      try { return await traerDescargas(); }
      catch (e) { return { disponible: false, motivo: e.message }; }
    })(),
  ]);

  // El panel se consulta a demanda; que no lo cachee ningún intermediario.
  res.setHeader('Cache-Control', 'no-store');
  return res.status(200).json({ generado: new Date().toISOString(), ventas, descargas });
}
