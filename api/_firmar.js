/**
 * Emisión de licencias, del lado del servidor.
 *
 * Vive en un archivo aparte porque hay dos caminos que llegan a lo mismo: el
 * pago aprobado de MercadoPago (`pago-confirmado.js`) y la emisión a mano
 * (`licencia.js`, para reponerle la licencia a un cliente o para la del dueño).
 * Si cada uno firmara por su cuenta, tarde o temprano uno de los dos quedaría
 * atrás y emitiría licencias que el programa rechaza.
 *
 * El archivo empieza con guión bajo a propósito: Vercel no lo publica como
 * ruta, sólo se puede importar.
 */
import crypto from 'node:crypto';

/** Días que dura cada plan. El sobrante es el margen de gracia del período. */
export const DIAS = {
  'profesional-mes': 31,
  'profesional-anio': 366,
  'empresa-mes': 31,
  'empresa-anio': 366,
};

export const b64url = (buf) =>
  Buffer.from(buf).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

/**
 * Arma el token con el mismo formato que verifica el programa: MVAS.payload.firma
 *
 * @param {'demo'|'paid'|'owner'} nivel
 * @param {string} titular
 * @param {number|null} dias  null = sin vencimiento (sólo para la licencia del dueño)
 * @param {string} clavePrivadaB64  la semilla Ed25519 de 32 bytes, en base64
 * @param {string} nota  queda dentro de la licencia; sirve para rastrear la venta
 */
export function emitirLicencia(nivel, titular, dias, clavePrivadaB64, nota = '') {
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

/**
 * Compara la clave del panel sin filtrar por cuánto tarda.
 * Una comparación común con `===` corta en la primera letra distinta, y ese
 * tiempo alcanza para adivinar la clave letra por letra.
 */
export function claveValida(recibida, esperada) {
  if (!esperada || !recibida) return false;
  const a = Buffer.from(String(recibida));
  const b = Buffer.from(String(esperada));
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

/**
 * Verifica un token de licencia con la clave pública. Es el mismo cálculo que
 * hace el programa en la máquina del cliente, y sirve para lo mismo: decidir si
 * quien golpea la puerta pagó.
 *
 * Devuelve la licencia si la firma es válida y no venció; `null` en cualquier
 * otro caso. No distingue entre «firma inválida» y «vencida» a propósito: el
 * que la manda no necesita saber cuál de las dos cosas falló.
 *
 * @param {string} token  MVAS.payload.firma
 * @param {string} publicaB64  clave pública Ed25519 en base64
 */
export function verificarLicencia(token, publicaB64) {
  try {
    const partes = String(token || '').split('.');
    if (partes.length !== 3 || partes[0] !== 'MVAS') return null;

    const deB64url = (s) => Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
    const payload = deB64url(partes[1]);
    const firma = deB64url(partes[2]);

    // Ed25519 en formato DER (SPKI): Node no acepta los 32 bytes crudos.
    const der = Buffer.concat([
      Buffer.from('302a300506032b6570032100', 'hex'),
      Buffer.from(publicaB64, 'base64'),
    ]);
    const clave = crypto.createPublicKey({ key: der, format: 'der', type: 'spki' });
    if (!crypto.verify(null, payload, clave, firma)) return null;

    const licencia = JSON.parse(payload.toString('utf8'));
    if (licencia.expires_at != null && licencia.expires_at < Date.now() / 1000) return null;
    return licencia;
  } catch {
    return null;
  }
}
