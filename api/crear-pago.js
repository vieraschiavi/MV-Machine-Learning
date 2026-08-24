/**
 * Crea el cobro en MercadoPago y devuelve el link al que mandar al comprador.
 *
 * El token de acceso NUNCA viaja al navegador: vive en la variable de entorno
 * `MP_ACCESS_TOKEN` de Vercel y sólo se usa acá, del lado del servidor. Poner
 * ese token en el HTML sería entregarle a cualquiera la llave para cobrar,
 * consultar pagos y hacer devoluciones en nombre del dueño de la cuenta.
 *
 * Variables de entorno:
 *   MP_ACCESS_TOKEN   credencial de MercadoPago (producción o prueba)
 *   SITIO             URL pública del sitio, para las páginas de retorno
 *   RESEND_API_KEY    opcional: si está, avisa por correo que alguien empezó a pagar
 *   CORREO_AVISOS     a dónde llega ese aviso
 */
import { avisar, horaLocal, yaAvisado } from './_avisar.js';

// Los precios viven acá, del lado del servidor: si dependieran de lo que manda
// el navegador, cualquiera podría comprar el plan Empresa por un peso.
const PLANES = {
  'profesional-mes': { titulo: 'MV AutoML Studio · Profesional (mensual)', precio: 39, meses: 1 },
  'profesional-anio': { titulo: 'MV AutoML Studio · Profesional (anual)', precio: 390, meses: 12 },
  'empresa-mes': { titulo: 'MV AutoML Studio · Empresa (mensual)', precio: 129, meses: 1 },
  'empresa-anio': { titulo: 'MV AutoML Studio · Empresa (anual)', precio: 1290, meses: 12 },
};

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Usá POST.' });
  }

  const token = process.env.MP_ACCESS_TOKEN;
  if (!token) {
    return res.status(503).json({
      error: 'El cobro todavía no está configurado en el servidor.',
      detalle: 'Falta la variable de entorno MP_ACCESS_TOKEN.',
    });
  }

  const { plan, email } = req.body || {};
  const elegido = PLANES[plan];
  if (!elegido) {
    return res.status(400).json({ error: `Plan desconocido: ${plan}` });
  }

  const sitio = process.env.SITIO || `https://${req.headers.host}`;
  const referencia = `${plan}:${Date.now()}`;

  try {
    const r = await fetch('https://api.mercadopago.com/checkout/preferences', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        items: [{
          title: elegido.titulo,
          quantity: 1,
          currency_id: 'USD',
          unit_price: elegido.precio,
        }],
        payer: email ? { email } : undefined,
        external_reference: referencia,
        back_urls: {
          success: `${sitio}/gracias.html`,
          pending: `${sitio}/gracias.html`,
          failure: `${sitio}/#precios`,
        },
        auto_return: 'approved',
        notification_url: `${sitio}/api/pago-confirmado`,
        statement_descriptor: 'MV SOFTWARE',
      }),
    });

    const datos = await r.json();
    if (!r.ok) {
      // El detalle de MercadoPago se registra pero no se le devuelve al
      // visitante: puede incluir información de la cuenta.
      console.error('MercadoPago rechazó la preferencia:', datos);
      return res.status(502).json({ error: 'No se pudo iniciar el cobro. Probá de nuevo.' });
    }

    // Aviso de que alguien arrancó un pago. Llega antes que el cobro
    // confirmado, así que sirve para saber que hay alguien decidiéndose ahora.
    //
    // Va DESPUÉS de tener el link y no se espera su resultado: si Resend está
    // caído o la clave falta, el comprador tiene que llegar igual al checkout.
    // Perder una venta por no poder avisar de ella sería absurdo.
    avisarDelIntento(elegido, plan, email, req).catch(() => {});

    return res.status(200).json({ url: datos.init_point, referencia });
  } catch (err) {
    console.error('Error creando la preferencia:', err);
    return res.status(502).json({ error: 'No se pudo iniciar el cobro. Probá de nuevo.' });
  }
}

/**
 * Avisa que alguien apretó comprar, una sola vez por persona y plan.
 *
 * La guarda importa porque el que duda toca el botón varias veces: sin ella,
 * un solo interesado manda cinco correos y el aviso deja de leerse.
 */
async function avisarDelIntento(elegido, plan, email, req) {
  const correo = String(email || '').trim().toLowerCase();
  // Sin correo se cae al origen del pedido: peor identificador, pero evita que
  // un mismo visitante anónimo dispare un aviso por clic.
  const quien = correo
    || String(req.headers['x-forwarded-for'] || '').split(',')[0].trim()
    || 'anónimo';
  if (yaAvisado(`pago:${quien}:${plan}`)) return;

  await avisar({
    asunto: `Alguien está comprando: ${elegido.titulo}`,
    responderA: correo || undefined,
    texto: [
      `Plan:    ${plan}`,
      `Monto:   US$ ${elegido.precio}`,
      `Correo:  ${correo || '(no lo dejó)'}`,
      `Hora:    ${horaLocal()}`,
      '',
      'Esto avisa que abrió el checkout, no que pagó. La confirmación del cobro',
      'llega por el webhook y es la que emite la licencia.',
    ].join('\n'),
  });
}
