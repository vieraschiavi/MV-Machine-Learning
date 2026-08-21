/**
 * Pedido de demo. No hay instalador público: quien quiere ver el programa deja
 * sus datos y se agenda una demostración en vivo.
 *
 * La decisión de fondo es comercial, no técnica: un instalador abierto regala
 * el artefacto de ingeniería a cualquiera que pase, incluida la competencia, y
 * deja que el interesado mire solo y se vaya sin dejar rastro. Con el pedido
 * queda registrado quién preguntó, desde qué empresa y con qué correo.
 *
 * El pedido llega por correo y también queda en los registros de Vercel, para
 * que un problema con el proveedor de correo no borre un contacto.
 *
 * Variables de entorno:
 *   RESEND_API_KEY   para enviar el aviso. Sin esto el pedido igual se registra.
 *   CORREO_AVISOS    a dónde llegan los pedidos (por omisión, el del dueño)
 *   CORREO_DESDE     remitente verificado
 */
const DESTINO = process.env.CORREO_AVISOS || 'vieraschiavi@gmail.com';

// Deliberadamente laxo: la validación de correos por expresión regular rechaza
// direcciones válidas si se pone exigente, y acá el costo de un falso negativo
// (perder un prospecto) es mucho mayor que el de un falso positivo.
const CORREO = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

const limpio = (v, tope) => String(v ?? '').replace(/\s+/g, ' ').trim().slice(0, tope);

function escapar(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

export function validar(cuerpo) {
  // Campo trampa: está oculto por CSS, así que una persona nunca lo completa.
  // Los robots que rellenan todo lo que encuentran caen acá.
  if (limpio(cuerpo?.web, 100)) return { error: 'No se pudo enviar el pedido.' };

  const datos = {
    nombre: limpio(cuerpo?.nombre, 120),
    empresa: limpio(cuerpo?.empresa, 120),
    pais: limpio(cuerpo?.pais, 80),
    correo: limpio(cuerpo?.correo, 160).toLowerCase(),
    telefono: limpio(cuerpo?.telefono, 60),
    mensaje: limpio(cuerpo?.mensaje, 2000),
  };

  if (datos.nombre.length < 3) return { error: 'Escribí tu nombre y apellido.' };
  if (datos.empresa.length < 2) return { error: 'Escribí el nombre de tu empresa.' };
  if (datos.pais.length < 2) return { error: 'Indicá desde qué país escribís.' };
  if (!CORREO.test(datos.correo)) return { error: 'Revisá la dirección de correo.' };

  return { datos };
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Usá POST.' });

  const { error, datos } = validar(req.body);
  if (error) return res.status(400).json({ error });

  const lineas = [
    `Nombre:   ${datos.nombre}`,
    `Empresa:  ${datos.empresa}`,
    `País:     ${datos.pais}`,
    `Correo:   ${datos.correo}`,
    datos.telefono ? `Teléfono: ${datos.telefono}` : '',
    '',
    datos.mensaje ? `Qué quiere analizar:\n${datos.mensaje}` : '(no dejó comentario)',
  ].filter((l) => l !== '').join('\n');

  // Primero el registro: si el correo falla, el contacto no se pierde.
  console.log(JSON.stringify({ pedido: 'demo', ...datos }));

  let avisado = false;
  if (process.env.RESEND_API_KEY) {
    try {
      const r = await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          from: process.env.CORREO_DESDE || 'MV Software <onboarding@resend.dev>',
          to: [DESTINO],
          // Respondiendo el correo se le contesta directo a quien pidió la demo.
          reply_to: datos.correo,
          subject: `Demo pedida: ${datos.empresa} (${datos.pais})`,
          text: lineas,
          html: `<pre style="font:14px/1.6 ui-monospace,monospace">${escapar(lineas)}</pre>`,
        }),
      });
      avisado = r.ok;
      if (!r.ok) console.error('Resend rechazó el aviso:', await r.text());
    } catch (e) {
      console.error('No se pudo avisar del pedido de demo:', e);
    }
  }

  res.setHeader('Cache-Control', 'no-store');
  // Al visitante se le confirma igual: el pedido quedó registrado del lado del
  // servidor, y que el correo haya salido o no es un problema nuestro, no suyo.
  return res.status(200).json({ ok: true, avisado });
}
