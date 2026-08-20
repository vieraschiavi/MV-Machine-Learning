/**
 * MercadoPago avisa acá cuando un pago cambia de estado. Si quedó aprobado,
 * se emite la licencia y se le manda al comprador.
 *
 * Dos cuidados que no son opcionales:
 *
 * 1. **No se confía en lo que llega.** El aviso sólo trae un id; el estado del
 *    pago se consulta contra la API de MercadoPago con el token del servidor.
 *    Si se confiara en el cuerpo del aviso, cualquiera podría mandar un POST
 *    diciendo «pagado» y llevarse una licencia gratis.
 * 2. **La clave privada de licencias vive sólo en el servidor**, en
 *    `MV_LICENSE_PRIVATE_KEY`. Es la misma con la que se firman los
 *    instaladores, y con ella se emiten licencias sin límite.
 *
 * Variables de entorno:
 *   MP_ACCESS_TOKEN          credencial de MercadoPago
 *   MV_LICENSE_PRIVATE_KEY   clave privada Ed25519 (base64), la del repositorio
 *   RESEND_API_KEY           opcional: si está, la licencia se manda por correo
 *   CORREO_DESDE             remitente verificado, p. ej. "MV Software <ventas@…>"
 */
import crypto from 'node:crypto';

const DIAS = { 'profesional-mes': 31, 'profesional-anio': 366,
               'empresa-mes': 31, 'empresa-anio': 366 };
const NIVEL = { 'profesional-mes': 'paid', 'profesional-anio': 'paid',
                'empresa-mes': 'paid', 'empresa-anio': 'paid' };

const b64url = (buf) =>
  Buffer.from(buf).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

/** Arma el token con el mismo formato que emite el programa: MVAS.payload.firma */
function emitirLicencia(nivel, titular, dias, clavePrivadaB64, nota = '') {
  const ahora = Date.now() / 1000;
  const licencia = {
    expires_at: dias == null ? null : ahora + dias * 86400,
    features: [],
    id: `lic_${crypto.randomBytes(6).toString('hex')}`,
    issued_at: ahora,
    licensee: titular,
    notes: nota,
    tier: nivel,
  };
  // Claves ordenadas y sin espacios: el verificador firma exactamente estos
  // bytes, así que cualquier diferencia de formato invalida la licencia.
  const payload = Buffer.from(JSON.stringify(licencia, Object.keys(licencia).sort()));

  // Ed25519 en formato DER: Node no acepta la semilla cruda directamente.
  const der = Buffer.concat([
    Buffer.from('302e020100300506032b657004220420', 'hex'),
    Buffer.from(clavePrivadaB64, 'base64'),
  ]);
  const clave = crypto.createPrivateKey({ key: der, format: 'der', type: 'pkcs8' });
  const firma = crypto.sign(null, payload, clave);
  return `MVAS.${b64url(payload)}.${b64url(firma)}`;
}

async function enviarPorCorreo(destino, licencia, plan) {
  const key = process.env.RESEND_API_KEY;
  if (!key || !destino) return false;
  const r = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: process.env.CORREO_DESDE || 'MV Software <onboarding@resend.dev>',
      to: [destino],
      subject: 'Tu licencia de MV AutoML Studio',
      text: [
        'Gracias por tu compra.',
        '',
        `Plan: ${plan}`,
        '',
        'Pegá este código en el programa, en la pantalla de inicio:',
        '',
        licencia,
        '',
        'Se activa al instante y no vence hasta el final del período contratado.',
        'Si tenés cualquier problema, respondé este correo.',
      ].join('\n'),
    }),
  });
  return r.ok;
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end();

  const token = process.env.MP_ACCESS_TOKEN;
  const clave = process.env.MV_LICENSE_PRIVATE_KEY;
  if (!token || !clave) {
    console.error('Falta MP_ACCESS_TOKEN o MV_LICENSE_PRIVATE_KEY');
    return res.status(200).end();          // no se le pide a MercadoPago que reintente
  }

  const id = req.body?.data?.id || req.query['data.id'];
  if (!id) return res.status(200).end();

  try {
    // El estado se consulta, no se cree: el aviso sólo dice qué mirar.
    const r = await fetch(`https://api.mercadopago.com/v1/payments/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const pago = await r.json();
    if (!r.ok || pago.status !== 'approved') {
      console.log(`pago ${id}: ${pago.status || 'no se pudo consultar'}`);
      return res.status(200).end();
    }

    const plan = String(pago.external_reference || '').split(':')[0];
    const dias = DIAS[plan];
    const nivel = NIVEL[plan];
    if (!dias) {
      console.error(`pago ${id} aprobado pero con plan desconocido: ${plan}`);
      return res.status(200).end();
    }

    const correo = pago.payer?.email || '';
    const titular = pago.payer?.first_name
      ? `${pago.payer.first_name} ${pago.payer.last_name || ''}`.trim()
      : correo || 'Cliente';

    // El plan queda anotado en la licencia: Profesional y Empresa habilitan hoy
    // lo mismo, así que sin esto no habría forma de saber cuál se vendió.
    const licencia = emitirLicencia(nivel, titular, dias, clave, `plan:${plan} pago:${id}`);
    const enviada = await enviarPorCorreo(correo, licencia, plan);

    // Queda en el registro de Vercel: si el correo no salió, la licencia se
    // puede recuperar de acá en vez de perderse.
    console.log(JSON.stringify({
      pago: id, plan, titular, correo, enviada, licencia,
    }));
    return res.status(200).end();
  } catch (err) {
    console.error('Error procesando el pago:', err);
    return res.status(200).end();
  }
}
