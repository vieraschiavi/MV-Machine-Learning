/**
 * Graba los videos del sitio recorriendo el programa de verdad.
 *
 * Existe porque la primera versión de estos videos se hizo a mano y no quedó
 * guión: cuando se corrigió el mapa de correlaciones en el programa, el video
 * siguió mostrando la versión rota y nadie tenía cómo rehacerlo. Un video que
 * no se puede regenerar envejece mal — muestra un producto que ya no existe.
 *
 * Qué hace:
 *   1. se conecta a un backend ya levantado, con un dataset y un modelo
 *      entrenado (los prepara `preparar()` si faltan);
 *   2. abre el programa en Chromium y lo recorre siguiendo los tiempos de
 *      `web/video/guiones.js`, para que la imagen acompañe a la narración;
 *   3. monta el audio ya sintetizado en `web/video/.audio/` y escribe el mp4
 *      y el webm en `web/video/`.
 *
 * Uso:
 *   MV_PORT=8912 MV_API_TOKEN=... node scripts/grabar_video.cjs recorrido es
 *   MV_PORT=8912 MV_API_TOKEN=... node scripts/grabar_video.cjs tablero en
 *
 * El audio NO se sintetiza acá: eso lo hace `web/video/generar_voz.py`. Si se
 * cambia el texto de la narración hay que correr ese primero.
 */
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');

/** ffmpeg explica sus fallas por stderr; sin esto llegan como un array de bytes. */
function ffmpeg(args) {
  try {
    return execFileSync(FFMPEG, args, { stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (e) {
    const detalle = (e.stderr || Buffer.alloc(0)).toString('utf8').trim().split('\n');
    throw new Error(`ffmpeg falló:\n${detalle.slice(-15).join('\n')}`);
  }
}
const fs = require('node:fs');
const path = require('node:path');

const RAIZ = path.resolve(__dirname, '..');
const DIR_VIDEO = path.join(RAIZ, 'web', 'video');
const AUDIO = path.join(DIR_VIDEO, '.audio');
const PORT = process.env.MV_PORT || '8912';
const TOKEN = process.env.MV_API_TOKEN || 'tok-video';
const BASE = `http://127.0.0.1:${PORT}`;
const NOMBRE = (process.argv[2] || 'recorrido').toLowerCase();
const IDIOMA = (process.argv[3] || 'es').toLowerCase();
const ANCHO = 1440;
const ALTO = 810;

// Chromium y ffmpeg vienen con Playwright; en este contenedor no están en PATH.
const buscar = (patron) => {
  const raiz = process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers';
  const dir = fs.readdirSync(raiz).find((d) => d.startsWith(patron));
  return dir ? path.join(raiz, dir) : null;
};
const CHROME = process.env.CHROME_BIN
  || path.join(buscar('chromium-') || '', 'chrome-linux', 'chrome');
// El ffmpeg que trae Playwright está compilado con `--disable-everything`: sólo
// sabe grabar webm mudo. No tiene ni códecs de audio ni los filtros para montar
// la narración, así que se prefiere uno completo. El de `imageio-ffmpeg` (que ya
// viene con las dependencias de Python) es una compilación estática entera.
const ffmpegCompleto = () => {
  const candidatos = [
    process.env.FFMPEG_BIN,
    ...['/usr/local/lib/python3.11/dist-packages', '/usr/lib/python3/dist-packages']
      .map((d) => path.join(d, 'imageio_ffmpeg', 'binaries'))
      .flatMap((d) => {
        try { return fs.readdirSync(d).map((f) => path.join(d, f)); } catch { return []; }
      })
      .filter((f) => path.basename(f).startsWith('ffmpeg-linux')),
    '/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg',
  ].filter(Boolean);
  for (const c of candidatos) {
    if (!fs.existsSync(c)) continue;
    try {
      const filtros = execFileSync(c, ['-hide_banner', '-filters'], { stdio: ['ignore', 'pipe', 'ignore'] });
      if (/\badelay\b/.test(filtros.toString())) return c;   // el recortado no lo tiene
    } catch { /* no sirve, se prueba el siguiente */ }
  }
  throw new Error('no hay un ffmpeg completo: hace falta uno con adelay/amix y códecs de audio');
};
const FFMPEG = ffmpegCompleto();

/** Los tiempos de la narración salen del guión, no de números sueltos acá. */
function guion(video, idioma) {
  const src = fs.readFileSync(path.join(DIR_VIDEO, 'guiones.js'), 'utf8');
  const window = {};
  new Function('window', src)(window);
  const tramos = window.NARRACION?.[video]?.[idioma];
  if (!tramos) throw new Error(`no hay guión para ${video}/${idioma}`);
  return tramos;
}

const api = async (ruta, opciones = {}) => {
  const r = await fetch(BASE + ruta, {
    ...opciones,
    headers: { 'X-MV-Token': TOKEN, ...(opciones.headers || {}) },
  });
  if (!r.ok) throw new Error(`${ruta} respondió ${r.status}`);
  return r.json();
};

// El dataset del video también habla el idioma del video.
//
// Los KPIs y los ejes se llaman como las columnas: filmando el archivo en
// castellano, el video en inglés mostraba `MontoDeuda` y `PromesasCumplidas`
// mientras la voz hablaba en inglés. Los números son los mismos en los tres
// —`examples/traducir.py` sólo renombra— así que los videos se pueden comparar
// cuadro a cuadro.
const DATOS = {
  es: { archivo: 'gestiones_con_texto.csv', nombre: 'gestiones_con_texto',
        objetivo: 'Pago30d', clave: 'IdGestion',
        panel: 'cobranzas_panel.xlsx', panelNombre: 'cobranzas_panel',
        pregunta: 'cual es el total cobrado' },
  en: { archivo: 'gestiones_con_texto-en.csv', nombre: 'collection_actions',
        objetivo: 'PaidIn30d', clave: 'ActionId',
        panel: 'cobranzas_panel-en.xlsx', panelNombre: 'collections_panel',
        pregunta: 'what is the total collected' },
  pt: { archivo: 'gestiones_con_texto-pt.csv', nombre: 'acoes_de_cobranca',
        objetivo: 'Pagou30d', clave: 'IdAcao',
        panel: 'cobranzas_panel-pt.xlsx', panelNombre: 'painel_de_cobrancas',
        pregunta: 'qual e o total recebido' },
};

/** Sube un archivo de `examples/` si ese dataset todavía no está cargado. */
async function dataset(archivo, nombre) {
  const { datasets = [] } = await api('/api/datasets');
  // Por nombre exacto: con una coincidencia parcial los tres idiomas se
  // quedaban con el primero que se hubiera cargado, y el video en inglés
  // terminaba filmando el dataset en castellano.
  const ya = datasets.find((d) => d.name === nombre);
  if (ya) return ya;
  const cuerpo = fs.readFileSync(path.join(RAIZ, 'examples', archivo));
  const q = new URLSearchParams({ filename: archivo, name: nombre });
  const r = await api(`/api/datasets/upload-stream?${q}`, { method: 'POST', body: cuerpo });
  console.log(`dataset cargado: ${r.dataset.id} (${nombre})`);
  return r.dataset;
}

/** Deja el programa con un dataset y un modelo entrenado para poder filmarlo. */
async function preparar() {
  const cfg = DATOS[IDIOMA] || DATOS.es;
  if (NOMBRE === 'tablero') return dataset(cfg.panel, cfg.panelNombre);
  const ds = await dataset(cfg.archivo, cfg.nombre);
  const { models = [] } = await api('/api/automl/models').catch(() => ({ models: [] }));
  if (!models.some((m) => m.dataset_id === ds.id)) {
    const job = await api('/api/automl/train', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataset_id: ds.id, target: cfg.objetivo, budget_seconds: 45, max_models: 3,
        shap: true, permutation_importance: true, exclude: [cfg.clave],
      }),
    });
    process.stdout.write('entrenando');
    for (let i = 0; i < 180; i++) {
      const st = await api(`/api/jobs/${job.id}`);
      if (st.status === 'terminado') { console.log(' · listo'); break; }
      if (st.status === 'error') throw new Error(st.error);
      process.stdout.write('.');
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
  return ds;
}

/** Qué se hace en pantalla en cada video, atado a los segundos del guion. */
function escenas(tramos) {
  return (NOMBRE === 'tablero' ? escenasTablero : escenasRecorrido)(tramos);
}

/** El tablero: se arma solo, se filtra, se exporta y se le pregunta. */
function escenasTablero(tramos) {
  const seg = (i) => tramos[i].t;
  const cfg = DATOS[IDIOMA] || DATOS.es;
  return [
    { en: 0, hacer: async (p) => {
        await p.evaluate(() => { location.hash = '#/dashboard'; });
        // El tablero se calcula al entrar: sin esperar a que aparezca un KPI,
        // los primeros segundos del video son un cartel de «Cargando».
        await p.waitForSelector('.stat-value, .kpi-value', { timeout: 30000 }).catch(() => {});
      } },
    { en: seg(2), hacer: async (p) => { await p.mouse.wheel(0, 300); } },
    { en: seg(3), hacer: async (p) => { await p.mouse.wheel(0, 320); } },
    { en: Math.max(0, seg(4) - 3), hacer: async (p) => {
        // Los filtros están arriba de todo: se vuelve a subir para que se vea
        // el clic y después el recálculo de los indicadores.
        await p.evaluate(() => window.scrollTo({ top: 0 }));
        const select = p.locator('.view.active select').nth(2);
        if (await select.count()) {
          const opciones = await select.locator('option').allTextContents();
          if (opciones.length > 1) await select.selectOption({ index: 1 });
        }
        const aplicar = p.locator('.view.active .btn-primary').first();
        if (await aplicar.count()) await aplicar.click({ timeout: 5000 }).catch(() => {});
      } },
    { en: seg(5), hacer: async (p) => { await p.mouse.wheel(0, 1400); } },
    { en: Math.max(0, seg(6) - 4), hacer: async (p) => {
        const caja = p.locator('.view.active input[type="text"]').last();
        if (!(await caja.count())) return;
        await caja.scrollIntoViewIfNeeded();
        await caja.click();
        // Se escribe con pausas: una pregunta que aparece de golpe no se lee
        // como alguien preguntando.
        await caja.type(cfg.pregunta, { delay: 55 });
        await p.keyboard.press('Enter');
      } },
  ];
}

/** El recorrido, atado a los segundos en que habla cada tramo. */
function escenasRecorrido(tramos) {
  const seg = (i) => tramos[i].t;
  return [
    { en: 0,      hacer: async (p) => { await p.evaluate(() => { location.hash = '#/overview'; }); } },
    { en: seg(1), hacer: async (p) => { await p.evaluate(() => { location.hash = '#/data'; }); } },
    { en: seg(1) + 5, hacer: async (p) => { await p.mouse.wheel(0, 320); } },
    // El mapa de correlaciones: la pantalla que motivó rehacer este video.
    //
    // Se abre ANTES de que la narración lo mencione y se espera a que el gráfico
    // exista de verdad. La primera vez que se pide, el backend tiene que
    // calcular la matriz, y eso tarda: sin esta espera el video mostraba un
    // panel vacío con un spinner justo mientras la voz decía «el mapa de
    // correlaciones muestra de una qué variables se mueven juntas».
    { en: Math.max(0, seg(2) - 4), hacer: async (p) => {
        await p.evaluate(() => { location.hash = '#/explore'; });
        await p.waitForSelector('.tab', { timeout: 15000 });
        await p.locator('.tab').nth(3).click();
        await p.waitForSelector('svg rect', { timeout: 30000 });
      } },
    { en: seg(3), hacer: async (p) => { await p.evaluate(() => { location.hash = '#/model'; }); } },
    { en: seg(4), hacer: async (p) => { await p.mouse.wheel(0, 380); } },
    { en: seg(5), hacer: async (p) => { await p.mouse.wheel(0, 380); } },
    { en: Math.max(0, seg(6) - 2), hacer: async (p) => {
        await p.evaluate(() => { location.hash = '#/results'; });
        // Mismo motivo: que el número del holdout esté en pantalla cuando la
        // voz lo dice, no dos segundos después.
        await p.waitForSelector('text=/0[.,]8/', { timeout: 20000 }).catch(() => {});
      } },
    { en: seg(7), hacer: async (p) => { await p.mouse.wheel(0, 700); } },
  ];
}

/** Une los tramos de audio en una sola pista, cada uno en su segundo. */
function pistaDeAudio(tramos, duracion, salida) {
  const partes = tramos
    .map((tr, i) => ({ tr, i, f: path.join(AUDIO, `${NOMBRE}-${IDIOMA}-${String(i).padStart(2, '0')}.mp3`) }))
    .filter((x) => fs.existsSync(x.f));
  if (!partes.length) throw new Error(`no hay audio en ${AUDIO} para ${IDIOMA}`);

  const entradas = partes.flatMap((x) => ['-i', x.f]);
  const retrasos = partes
    .map((x, k) => `[${k}:a]adelay=${Math.round(x.tr.t * 1000)}|${Math.round(x.tr.t * 1000)}[a${k}]`)
    .join(';');
  const mezcla = partes.map((_, k) => `[a${k}]`).join('');
  ffmpeg([
    '-y', ...entradas,
    '-filter_complex',
    `${retrasos};${mezcla}amix=inputs=${partes.length}:normalize=0:dropout_transition=0[out]`,
    '-map', '[out]', '-t', String(duracion), '-ac', '2', '-ar', '48000', salida,
  ], { stdio: 'pipe' });
  return salida;
}

(async () => {
  if (!fs.existsSync(CHROME)) throw new Error(`no encuentro Chromium en ${CHROME}`);
  console.log(`ffmpeg: ${FFMPEG}`);
  const tramos = guion(NOMBRE, IDIOMA);
  const duracion = Math.ceil(tramos[tramos.length - 1].t) + 11;   // cola para leer la última pantalla
  console.log(`${NOMBRE}-${IDIOMA}: ${tramos.length} tramos, ${duracion} s`);

  const ds = await preparar();

  const tmp = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'mv-video-'));
  const navegador = await chromium.launch({ executablePath: CHROME });
  const ctx = await navegador.newContext({
    viewport: { width: ANCHO, height: ALTO },
    deviceScaleFactor: 1,
    recordVideo: { dir: tmp, size: { width: ANCHO, height: ALTO } },
  });
  const p = await ctx.newPage();

  // El token viaja como lo inyecta Electron (`window.mvDesktop`), que es de
  // donde lo lee el cliente HTTP del programa. El idioma se fija antes de
  // cargar para que la interfaz ya arranque en el idioma del video.
  await p.addInitScript(([tok, idioma, dsId]) => {
    window.mvDesktop = { token: tok };
    localStorage.setItem('mv.lang', idioma);
    localStorage.setItem('mv.theme', 'dark');
    // El dataset del video queda elegido de entrada. Si no, el tablero abre en
    // «elegí un dataset» durante los primeros segundos, que son justo los que
    // la narración usa para decir que se arma solo.
    if (dsId) localStorage.setItem('mv.dataset', dsId);
  }, [TOKEN, IDIOMA, ds?.id || '']);
  await p.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await p.waitForTimeout(1500);

  const arranque = Date.now();
  const esperarHasta = async (s) => {
    const falta = arranque + s * 1000 - Date.now();
    if (falta > 0) await p.waitForTimeout(falta);
  };
  for (const escena of escenas(tramos)) {
    await esperarHasta(escena.en);
    try { await escena.hacer(p); } catch (e) { console.warn(`escena en ${escena.en}s: ${e.message}`); }
  }
  await esperarHasta(duracion);

  await ctx.close();          // recién acá Playwright termina de escribir el webm
  await navegador.close();

  const crudo = fs.readdirSync(tmp).find((f) => f.endsWith('.webm'));
  if (!crudo) throw new Error('Playwright no dejó ningún video');
  const mudo = path.join(tmp, crudo);
  const voz = pistaDeAudio(tramos, duracion, path.join(tmp, 'voz.m4a'));

  const mp4 = path.join(DIR_VIDEO, `${NOMBRE}-${IDIOMA}.mp4`);
  const webm = path.join(DIR_VIDEO, `${NOMBRE}-${IDIOMA}.webm`);
  // `-shortest` con `apad` acotado: sin el tope, el silencio de relleno es
  // infinito y la codificación no termina nunca.
  const comun = ['-y', '-i', mudo, '-i', voz,
    '-filter_complex', `[1:a]apad=whole_dur=${duracion}[a]`,
    '-map', '0:v', '-map', '[a]', '-t', String(duracion)];
  ffmpeg([...comun, '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', mp4]);
  ffmpeg([...comun, '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '34',
    '-row-mt', '1', '-c:a', 'libopus', '-b:a', '96k', webm]);

  fs.rmSync(tmp, { recursive: true, force: true });
  for (const f of [mp4, webm]) {
    console.log(`${path.basename(f)}: ${(fs.statSync(f).size / 1048576).toFixed(1)} MB`);
  }
})();
