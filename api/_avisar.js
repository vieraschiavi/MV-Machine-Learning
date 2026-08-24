/**
 * Avisos por correo al dueño, y la guarda para no mandar el mismo cinco veces.
 *
 * Hay dos momentos en que conviene enterarse: cuando alguien **pide una demo** y
 * cuando alguien **arranca un pago**. El segundo llega antes que el cobro
 * confirmado, así que sirve para saber que hay alguien decidiéndose ahora — pero
 * también es el que más se repite, porque el que duda toca el botón varias veces.
 *
 * Variables de entorno:
 *   RESEND_API_KEY   sin esto no se manda nada (y no se rompe nada)
 *   CORREO_AVISOS    a dónde llegan
 *   CORREO_DESDE     remitente verificado
 */
const DESTINO = () => process.env.CORREO_AVISOS || 'vieraschiavi@gmail.com';

/**
 * Recuerda qué se avisó hace poco.
 *
 * Vive en memoria del proceso a propósito: no hay base de datos en este
 * proyecto y no vale la pena agregar una para esto. La contra es real y hay que
 * decirla: Vercel puede levantar varias instancias, y dos clics atendidos por
 * instancias distintas pasan los dos. Igual tapa el caso que molesta —el mismo
 * visitante insistiendo en los próximos minutos— porque esos clics caen casi
 * siempre en la misma instancia tibia.
 */
const vistos = new Map();
const VENTANA = 30 * 60 * 1000;          // media hora

export function yaAvisado(clave, ahora = Date.now(), ventana = VENTANA) {
  // De paso se limpia lo vencido: sin esto el mapa crece para siempre en una
  // instancia de vida larga.
  for (const [k, t] of vistos) if (ahora - t > ventana) vistos.delete(k);

  const previo = vistos.get(clave);
  if (previo != null && ahora - previo <= ventana) return true;
  vistos.set(clave, ahora);
  return false;
}

/** Sólo para las pruebas: deja la memoria como recién arrancada. */
export function olvidarAvisos() { vistos.clear(); }

const escapar = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/**
 * Manda el aviso. Nunca lanza: un problema con el correo no puede voltear la
 * operación que lo disparó — sería perder una venta por no poder avisar de ella.
 *
 * @returns {Promise<boolean>} si salió o no
 */
export async function avisar({ asunto, texto, responderA }) {
  const key = process.env.RESEND_API_KEY;
  if (!key) return false;
  try {
    const r = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from: process.env.CORREO_DESDE || 'MV Software <onboarding@resend.dev>',
        to: [DESTINO()],
        ...(responderA ? { reply_to: responderA } : {}),
        subject: asunto,
        text: texto,
        html: `<pre style="font:14px/1.6 ui-monospace,monospace">${escapar(texto)}</pre>`,
      }),
    });
    if (!r.ok) console.error('Resend rechazó el aviso:', await r.text());
    return r.ok;
  } catch (e) {
    console.error('No se pudo mandar el aviso:', e);
    return false;
  }
}

/** Hora de Montevideo, que es la que le sirve al que lee el aviso. */
export function horaLocal(fecha = new Date()) {
  return fecha.toLocaleString('es-UY', {
    timeZone: 'America/Montevideo',
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}
