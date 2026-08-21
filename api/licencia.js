/**
 * Emisión de licencias a mano, para las dos veces que hace falta:
 *
 *   1. **La licencia de dueño.** Sin límites y sin vencimiento, para validar el
 *      programa completo sin depender de una compilación.
 *   2. **Reponer una compra.** El cliente pagó, el correo se perdió o cayó en
 *      spam, y hay que mandarle su licencia de nuevo sin hacerlo pagar otra vez.
 *
 * Está detrás de la misma clave que el panel (`PANEL_CLAVE`). Quien entre acá
 * puede emitir licencias gratis, así que esa clave es tan sensible como la
 * privada de firma.
 *
 * Variables de entorno:
 *   PANEL_CLAVE              contraseña del panel
 *   MV_LICENSE_PRIVATE_KEY   clave privada Ed25519 (base64)
 *   RESEND_API_KEY           opcional: si está y se pasa un correo, se envía
 *   CORREO_DESDE             remitente verificado
 *   SITIO                    URL pública, para armar el enlace de descarga
 */
import { DIAS, claveValida, emitirLicencia } from './_firmar.js';

const NIVELES = new Set(['demo', 'paid', 'owner']);

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Usá POST.' });

  const esperada = process.env.PANEL_CLAVE;
  if (!esperada) {
    return res.status(503).json({ error: 'Falta PANEL_CLAVE en el servidor.' });
  }
  if (!claveValida(req.headers['x-mv-panel'], esperada)) {
    return res.status(401).json({ error: 'Clave incorrecta.' });
  }

  const privada = process.env.MV_LICENSE_PRIVATE_KEY;
  if (!privada) {
    return res.status(503).json({
      error: 'Falta MV_LICENSE_PRIVATE_KEY en el servidor.',
      detalle: 'Generá el par en /claves y cargalo en Vercel.',
    });
  }

  const { nivel = 'paid', titular = 'Cliente', plan, dias, nota = '', correo } = req.body || {};
  if (!NIVELES.has(nivel)) {
    return res.status(400).json({ error: `Nivel desconocido: ${nivel}` });
  }

  // Prioridad: los días que se pidan explícitamente, si no los del plan, y la
  // licencia de dueño sin vencimiento. Un `paid` sin ninguna de las dos cosas
  // sería una licencia eterna vendida por error, así que se rechaza.
  let duracion = null;
  if (dias != null) duracion = Number(dias);
  else if (plan && DIAS[plan]) duracion = DIAS[plan];
  else if (nivel !== 'owner') {
    return res.status(400).json({
      error: 'Indicá "plan" (profesional-mes, profesional-anio, empresa-mes, '
           + 'empresa-anio) o "dias".',
    });
  }
  if (duracion != null && (!isFinite(duracion) || duracion <= 0 || duracion > 3660)) {
    return res.status(400).json({ error: 'La cantidad de días no es razonable.' });
  }

  const detalle = [plan ? `plan:${plan}` : '', nota, 'emision:manual']
    .filter(Boolean).join(' ');
  const licencia = emitirLicencia(nivel, titular, duracion, privada, detalle);

  // El instalador no es público: el enlace de descarga va atado a la licencia y
  // es lo único que le sirve al que la recibe.
  const sitio = process.env.SITIO || `https://${req.headers?.host || ''}`;
  const descarga = `${sitio}/api/descargar?lic=${encodeURIComponent(licencia)}`;

  let enviada = false;
  if (correo && process.env.RESEND_API_KEY) {
    try {
      const r = await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          from: process.env.CORREO_DESDE || 'MV Software <onboarding@resend.dev>',
          to: [correo],
          subject: 'Tu licencia de MV AutoML Studio',
          text: [
            'Acá va tu licencia de MV AutoML Studio.',
            '',
            '1 · Descargá el instalador desde este enlace, que es tuyo:',
            '',
            descarga,
            '',
            '2 · Abrí el programa y pegá este código en la pantalla de inicio:',
            '',
            licencia,
            '',
            'Se activa al instante, sin reinstalar.',
          ].join('\n'),
        }),
      });
      enviada = r.ok;
    } catch (e) {
      console.error('No se pudo enviar la licencia por correo:', e);
    }
  }

  // Queda registrada: si alguien emite una licencia que no corresponde, el
  // rastro está en los registros de Vercel.
  console.log(JSON.stringify({ emision: 'manual', nivel, titular, plan, dias: duracion, correo, enviada }));
  res.setHeader('Cache-Control', 'no-store');
  return res.status(200).json({ licencia, descarga, nivel, dias: duracion, titular, enviada });
}
