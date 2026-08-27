/**
 * Qué falta para vender: el diagnóstico de la configuración.
 *
 * Todo el circuito comercial —cobrar, emitir la licencia, mandarla por correo,
 * entregar el instalador, abrir el panel— depende de nueve variables cargadas
 * en el servidor. Cuando falta una, lo que se ve es un error puntual en el
 * momento menos oportuno: el cliente pagó y no le llega nada, o el botón de
 * compra no cobra. El síntoma no dice cuál es la variable.
 *
 * Esto lo dice de frente y en un solo lugar: qué está cargado, qué falta, qué
 * se rompe con cada faltante y de dónde sale el valor. Y con `?probar=1`, en
 * vez de mirar si la variable existe, la usa: le pregunta a MercadoPago, a
 * Resend y a GitHub si la credencial sirve. Una clave mal pegada está
 * «cargada» y no funciona.
 *
 * Nunca devuelve un valor, ni recortado: sólo si está y si anda.
 *
 * Uso:
 *   GET /api/estado                    resumen (cuántas faltan)
 *   GET /api/estado?probar=1           además, prueba las credenciales
 *   con la cabecera `x-mv-panel`       el detalle variable por variable
 *
 * El detalle sale sin clave mientras `PANEL_CLAVE` no esté cargada, que es
 * justo cuando hace falta: si no, para saber qué configurar habría que tener
 * configurado el panel.
 */
import { claveValida } from './_firmar.js';

const VARIABLES = [
  {
    nombre: 'MV_LICENSE_PRIVATE_KEY',
    para: 'Firmar las licencias que se venden.',
    siFalta: 'El pago entra pero no se emite ninguna licencia.',
    deDonde: 'Se genera en /claves, dentro de tu navegador. No se comparte.',
    critica: true,
  },
  {
    nombre: 'MV_LICENSE_PUBLIC_KEY',
    para: 'Verificar esas licencias. Va adentro de cada instalador.',
    siFalta: 'Quien compró no puede descargar el instalador.',
    deDonde: 'Sale del mismo botón que la privada. No es secreta.',
    critica: true,
  },
  {
    nombre: 'MP_ACCESS_TOKEN',
    para: 'Cobrar y confirmar los pagos contra MercadoPago.',
    siFalta: 'El botón de compra no cobra.',
    deDonde: 'MercadoPago → Desarrolladores → tu aplicación → Credenciales.',
    critica: true,
  },
  {
    nombre: 'GITHUB_TOKEN',
    para: 'Sacar el instalador del release en borrador y entregarlo.',
    siFalta: 'La descarga no funciona, ni para el cliente ni para el dueño.',
    deDonde: 'GitHub → Developer settings → token de sólo lectura del repo.',
    critica: true,
  },
  {
    nombre: 'PANEL_CLAVE',
    para: 'Entrar al panel de ventas y emitir licencias a mano.',
    siFalta: 'El panel queda cerrado y no se pueden emitir licencias.',
    deDonde: 'La inventás vos: una frase larga que no uses en otro lado.',
    critica: true,
  },
  {
    nombre: 'RESEND_API_KEY',
    para: 'Mandarle la licencia al que compra y avisarte de los pedidos de demo.',
    siFalta: 'El cliente paga y no recibe nada por correo.',
    deDonde: 'resend.com → API Keys → Create API Key (Sending access).',
    critica: true,
  },
  {
    nombre: 'CORREO_DESDE',
    para: 'El remitente de esos correos.',
    siFalta: 'Salen desde una dirección de prueba y caen en spam.',
    deDonde: 'Lo escribís vos: MV Software <ventas@tudominio.com>.',
    critica: false,
  },
  {
    nombre: 'CORREO_AVISOS',
    para: 'Dónde te llegan los pedidos de demo.',
    siFalta: 'Se usa la dirección por omisión del código.',
    deDonde: 'Tu dirección de correo.',
    critica: false,
  },
  {
    nombre: 'SITIO',
    para: 'Armar los enlaces de descarga que van en el correo.',
    siFalta: 'Los enlaces salen mal armados.',
    deDonde: 'La URL pública del sitio, con https y sin barra final.',
    critica: false,
  },
];

const puesta = (v) => Boolean((process.env[v] || '').trim());

/** Le pregunta a cada servicio si la credencial sirve de verdad. */
async function probarCredenciales() {
  const pedir = async (url, opciones) => {
    const corte = AbortSignal.timeout(6000);
    try {
      const r = await fetch(url, { ...opciones, signal: corte });
      return r.ok ? { anda: true }
        : { anda: false, detalle: `respondió ${r.status}` };
    } catch (e) {
      return { anda: false, detalle: e.name === 'TimeoutError' ? 'no contestó' : e.message };
    }
  };

  const pruebas = {};
  if (puesta('MP_ACCESS_TOKEN')) {
    pruebas.MP_ACCESS_TOKEN = await pedir(
      'https://api.mercadopago.com/users/me',
      { headers: { Authorization: `Bearer ${process.env.MP_ACCESS_TOKEN}` } });
  }
  if (puesta('RESEND_API_KEY')) {
    pruebas.RESEND_API_KEY = await pedir(
      'https://api.resend.com/domains',
      { headers: { Authorization: `Bearer ${process.env.RESEND_API_KEY}` } });
  }
  if (puesta('GITHUB_TOKEN')) {
    const repo = process.env.REPO || 'vieraschiavi/MV-Machine-Learning';
    pruebas.GITHUB_TOKEN = await pedir(
      `https://api.github.com/repos/${repo}`,
      { headers: { Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
                   Accept: 'application/vnd.github+json' } });
  }
  // Las dos claves de licencia no se prueban contra nadie: se prueban entre
  // ellas. Un par que no se corresponde firma licencias que el propio sitio
  // rechaza después, y eso no se descubre hasta la primera venta.
  if (puesta('MV_LICENSE_PRIVATE_KEY') && puesta('MV_LICENSE_PUBLIC_KEY')) {
    try {
      const { emitirLicencia, verificarLicencia } = await import('./_firmar.js');
      const prueba = emitirLicencia('demo', 'Prueba de configuración', 1,
                                    process.env.MV_LICENSE_PRIVATE_KEY);
      pruebas.MV_LICENSE_PRIVATE_KEY = verificarLicencia(prueba, process.env.MV_LICENSE_PUBLIC_KEY)
        ? { anda: true }
        : { anda: false, detalle: 'la privada y la pública no son del mismo par' };
    } catch (e) {
      pruebas.MV_LICENSE_PRIVATE_KEY = { anda: false, detalle: e.message };
    }
  }
  return pruebas;
}

export default async function handler(req, res) {
  const clave = process.env.PANEL_CLAVE;
  // Sin PANEL_CLAVE cargada no hay con qué autenticarse, y es justo el momento
  // en que este diagnóstico sirve. Una vez cargada, el detalle pide la clave.
  const detallado = !clave || claveValida(req.headers['x-mv-panel'], clave);

  const estado = VARIABLES.map((v) => ({ ...v, cargada: puesta(v.nombre) }));
  const faltan = estado.filter((v) => !v.cargada);
  const faltanCriticas = faltan.filter((v) => v.critica);

  const cuerpo = {
    listo: faltanCriticas.length === 0,
    cargadas: estado.length - faltan.length,
    total: estado.length,
    faltan: faltan.length,
    faltan_criticas: faltanCriticas.length,
  };

  if (detallado) {
    if (req.query?.probar) cuerpo.pruebas = await probarCredenciales();
    cuerpo.variables = estado.map((v) => ({
      nombre: v.nombre,
      cargada: v.cargada,
      critica: v.critica,
      para: v.para,
      si_falta: v.siFalta,
      de_donde_sale: v.deDonde,
      ...(cuerpo.pruebas?.[v.nombre] ? { prueba: cuerpo.pruebas[v.nombre] } : {}),
    }));
    delete cuerpo.pruebas;
    cuerpo.documentacion = 'docs/PRODUCCION.md explica cada una, paso a paso.';
  } else {
    cuerpo.detalle = 'Mandá la cabecera x-mv-panel con la clave del panel para '
      + 'ver qué falta variable por variable.';
  }

  res.setHeader('Cache-Control', 'no-store');
  return res.status(200).json(cuerpo);
}
