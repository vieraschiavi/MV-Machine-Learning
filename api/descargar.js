/**
 * Descarga del instalador, sólo para quien tiene licencia.
 *
 * El instalador dejó de publicarse abierto: el release queda en borrador y sus
 * archivos no son alcanzables sin credenciales. Esta función es la única puerta.
 *
 * Cómo funciona: el cliente llega con su licencia en la dirección
 * (`/api/descargar?lic=MVAS.…`), se verifica la firma contra la clave pública
 * —el mismo cálculo que hace el programa— y, si es buena, se le devuelve una
 * redirección a un enlace firmado por GitHub que vence en unos minutos.
 *
 * El archivo nunca pasa por acá. Una función serverless no puede servir 375 MB,
 * y aunque pudiera sería pagar ancho de banda para hacer de intermediario: se
 * pide el enlace temporal y se manda al cliente directo a buscarlo.
 *
 * Una licencia de nivel `owner` recibe el instalador OWNER, que trae la
 * licencia de dueño adentro. Es la forma de bajar la versión completa sin
 * entrar a la interfaz de GitHub ni manejar tokens: la licencia que ya
 * identifica al dueño alcanza para pedirla.
 *
 * Variables de entorno:
 *   MV_LICENSE_PUBLIC_KEY  clave pública Ed25519 (base64). No es secreta.
 *   GITHUB_TOKEN           token con permiso de lectura del repositorio
 *   REPO                   opcional: "usuario/repositorio"
 *   ARCHIVO_INSTALADOR     opcional: nombre del .exe a entregar
 *   ARCHIVO_INSTALADOR_OWNER  opcional: nombre del .exe de dueño
 */
import { verificarLicencia } from './_firmar.js';

const REPO = process.env.REPO || 'vieraschiavi/MV-Machine-Learning';
const ARCHIVO = process.env.ARCHIVO_INSTALADOR || 'MV-AutoML-Studio-Setup.exe';
const ARCHIVO_OWNER = process.env.ARCHIVO_INSTALADOR_OWNER
  || 'MV-AutoML-Studio-Owner-Setup.exe';

/** Busca el instalador en el release más reciente que lo tenga. */
async function ubicarInstalador(gh, archivo = ARCHIVO) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/releases?per_page=30`, {
    headers: { Authorization: `Bearer ${gh}`, Accept: 'application/vnd.github+json' },
  });
  if (!r.ok) throw new Error(`GitHub respondió ${r.status} al listar releases`);
  const releases = await r.json();
  for (const rel of releases) {
    for (const a of rel.assets || []) {
      if (a.name === archivo) return a.url;      // la API los devuelve del más nuevo al más viejo
    }
  }
  throw new Error(`no hay ningún release con ${archivo}`);
}

/** Pide a GitHub el enlace temporal al archivo. */
async function enlaceTemporal(assetUrl, gh) {
  const r = await fetch(assetUrl, {
    headers: { Authorization: `Bearer ${gh}`, Accept: 'application/octet-stream' },
    redirect: 'manual',
  });
  const destino = r.headers.get('location');
  if (!destino) throw new Error(`GitHub no devolvió el enlace (HTTP ${r.status})`);
  return destino;
}

export default async function handler(req, res) {
  const publica = process.env.MV_LICENSE_PUBLIC_KEY;
  const gh = process.env.GITHUB_TOKEN;
  if (!publica || !gh) {
    console.error('Falta MV_LICENSE_PUBLIC_KEY o GITHUB_TOKEN');
    return res.status(503).json({
      error: 'La descarga todavía no está configurada.',
      detalle: 'Faltan MV_LICENSE_PUBLIC_KEY o GITHUB_TOKEN en el servidor.',
    });
  }

  const token = req.query?.lic || req.body?.lic;
  const licencia = verificarLicencia(token, publica);
  if (!licencia) {
    // Un solo mensaje para licencia inválida, vencida o ausente: no hay por qué
    // ayudar a alguien a distinguir «casi» de «no».
    return res.status(403).json({
      error: 'Esa licencia no es válida o venció.',
      detalle: 'Usá el enlace del correo de tu compra, o escribinos.',
    });
  }

  // El dueño se lleva la compilación de dueño. Es el mismo camino que el del
  // cliente —la licencia entra por la dirección y sale un enlace temporal—, así
  // que probar la versión completa no pide nada más que la licencia que ya
  // tiene: ni entrar a GitHub, ni un token, ni bajar un release borrador a mano.
  const archivo = licencia.tier === 'owner' ? ARCHIVO_OWNER : ARCHIVO;

  try {
    const destino = await enlaceTemporal(await ubicarInstalador(gh, archivo), gh);
    // Queda registrado quién bajó y cuándo, sin guardar la licencia entera.
    console.log(JSON.stringify({
      descarga: licencia.id, nivel: licencia.tier, titular: licencia.licensee,
      archivo,
    }));
    res.setHeader('Cache-Control', 'no-store');
    return res.redirect(302, destino);
  } catch (e) {
    // El cliente pagó: si algo falla del lado nuestro, se lo decimos y le damos
    // una salida, en vez de dejarlo mirando un error.
    console.error('No se pudo entregar el instalador:', e);
    return res.status(502).json({
      error: 'No pudimos preparar la descarga en este momento.',
      detalle: 'Probá de nuevo en un minuto. Si sigue fallando, escribinos y te la mandamos.',
    });
  }
}
