/**
 * MV AutoML Studio — proceso principal de Electron.
 *
 * Responsabilidades, en orden:
 *   1. generar el token de sesión y lanzar el backend con él (la API en
 *      127.0.0.1 no queda abierta a cualquier proceso del equipo);
 *   2. esperar a que el backend responda y recién entonces abrir la ventana;
 *   3. inyectar el token a la interfaz por el puente seguro (preload);
 *   4. al cerrar, apagar el backend sin dejar procesos huérfanos.
 *
 * En una compilación owner, `resources/owner/license.key` viaja embebida y se
 * pasa al backend por entorno: la aplicación arranca con el nivel completo.
 */
const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');

const { carpetaDeDatos } = require('./carpeta-datos.cjs');

const PORT = 8474;                       // puerto propio, lejos de los típicos
const TOKEN = crypto.randomBytes(32).toString('base64url');

let backend = null;
let ventana = null;
let apagando = false;

/* ── una sola instancia ──────────────────────────────────────────────────── */
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (ventana) {
      if (ventana.isMinimized()) ventana.restore();
      ventana.focus();
    }
  });
}

/* ── rutas ───────────────────────────────────────────────────────────────── */
function recursos(...p) {
  return app.isPackaged
    ? path.join(process.resourcesPath, ...p)
    : path.join(__dirname, '..', '..', ...p);
}

function rutaBackend() {
  if (app.isPackaged) {
    const exe = process.platform === 'win32' ? 'mv-backend.exe' : 'mv-backend';
    return { cmd: path.join(process.resourcesPath, 'mv-backend', exe), args: [] };
  }
  // en desarrollo se usa el Python del sistema contra el código fuente
  return {
    cmd: process.platform === 'win32' ? 'python' : 'python3',
    args: ['-m', 'uvicorn', 'backend.app.main:app',
           '--host', '127.0.0.1', '--port', String(PORT), '--log-level', 'warning'],
  };
}

/* ── licencia embebida (compilación owner) ───────────────────────────────── */
function licenciaEmbebida() {
  const out = {};
  const lic = recursos('owner', 'license.key');
  const pub = recursos('owner', 'public.key');
  try {
    if (fs.existsSync(lic)) out.MV_LICENSE = fs.readFileSync(lic, 'utf8').trim();
    if (fs.existsSync(pub)) out.MV_LICENSE_PUBLIC_KEY = fs.readFileSync(pub, 'utf8').trim();
  } catch { /* sin licencia embebida: arranca en demo */ }
  return out;
}

/* ── backend ─────────────────────────────────────────────────────────────── */
function lanzarBackend() {
  const { cmd, args } = rutaBackend();
  // Puede terminar fuera del disco del sistema: ver `carpeta-datos.cjs`.
  const datos = carpetaDeDatos({
    entorno: process.env.MV_DATA_DIR,
    empaquetado: app.isPackaged,
    raizDelPrograma: app.isPackaged ? path.dirname(process.resourcesPath) : '',
    perfilDelUsuario: app.getPath('userData'),
  });
  fs.mkdirSync(datos, { recursive: true });

  backend = spawn(cmd, args, {
    cwd: app.isPackaged ? path.dirname(cmd) : recursos(),
    env: {
      ...process.env,
      MV_HOST: '127.0.0.1',
      MV_PORT: String(PORT),
      MV_API_TOKEN: TOKEN,
      MV_DATA_DIR: datos,               // ver `carpeta-datos.cjs`
      // Sin esto el backend busca la interfaz junto al código fuente, que
      // dentro del .exe no existe: no monta ni `/assets` ni la raíz, y la
      // ventana abre mostrando {"detail": "Not Found"} en vez del programa.
      // `electron-builder.yml` la empaqueta en `resources/frontend`.
      MV_FRONTEND_DIR: recursos('frontend'),
      ...licenciaEmbebida(),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  backend.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backend.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  backend.on('exit', (code) => {
    backend = null;
    if (!apagando && code !== 0) {
      dialog.showErrorBox('MV AutoML Studio',
        `El motor se cerró de forma inesperada (código ${code}). ` +
        'Reabrí la aplicación; si persiste, revisá el registro.');
      app.quit();
    }
  });
}

function esperarBackend(intentos = 120) {
  return new Promise((resolve, reject) => {
    const tick = (n) => {
      const req = http.get({ host: '127.0.0.1', port: PORT, path: '/api/health', timeout: 900 },
        (res) => { res.resume(); res.statusCode === 200 ? resolve() : reintentar(n); });
      req.on('error', () => reintentar(n));
      req.on('timeout', () => { req.destroy(); reintentar(n); });
    };
    const reintentar = (n) => (n <= 0
      ? reject(new Error('El motor no respondió en 60 segundos.'))
      : setTimeout(() => tick(n - 1), 500));
    tick(intentos);
  });
}

/* ── ventana ─────────────────────────────────────────────────────────────── */
function crearVentana() {
  ventana = new BrowserWindow({
    width: 1440, height: 940, minWidth: 980, minHeight: 640,
    show: false,
    backgroundColor: '#101114',
    icon: recursos('desktop', 'build', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [`--mv-token=${TOKEN}`],
    },
  });
  ventana.loadURL(`http://127.0.0.1:${PORT}/`);
  ventana.once('ready-to-show', () => ventana.show());

  // los links externos van al navegador del sistema, nunca dentro de la app
  ventana.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) shell.openExternal(url);
    return { action: 'deny' };
  });
  ventana.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith(`http://127.0.0.1:${PORT}`)) {
      e.preventDefault();
      if (url.startsWith('https://')) shell.openExternal(url);
    }
  });
  ventana.on('closed', () => { ventana = null; });
}

/* ── guardar un documento del backend como PDF ───────────────────────────── */
/**
 * La bitácora se exporta en HTML y ese mismo HTML es el PDF: se imprime acá,
 * sin diálogo de impresora y sin sumarle al instalador una biblioteca de PDF
 * —Chromium ya sabe hacerlo—. Que los dos formatos salgan del mismo documento
 * es lo que evita que con el tiempo digan cosas distintas.
 *
 * La dirección llega desde la interfaz, así que se valida antes de abrirla:
 * sólo se imprime lo que sirve el backend local, en su puerto. Sin ese
 * control, esto dejaría de ser un exportador y pasaría a ser una forma de
 * cargar cualquier página adentro del programa.
 */
ipcMain.handle('mv:guardar-pdf', async (_evento, { url, nombre } = {}) => {
  const permitido = `http://127.0.0.1:${PORT}/`;
  if (typeof url !== 'string' || !url.startsWith(permitido)) {
    return { ok: false, error: 'Dirección no permitida.' };
  }

  // `ventana` es null si el usuario ya la cerró: showSaveDialog con null
  // revienta, y sin padre abre igual, suelto.
  const destino = await dialog.showSaveDialog(ventana || undefined, {
    title: 'Guardar la bitácora en PDF',
    defaultPath: nombre || 'MV-Bitacora.pdf',
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  });
  if (destino.canceled || !destino.filePath) return { ok: false, cancelado: true };

  // Ventana propia y oculta: imprimir la ventana visible saldría con el menú
  // lateral y el documento cortado por el alto de la pantalla.
  const oculta = new BrowserWindow({
    show: false,
    webPreferences: { sandbox: true, nodeIntegration: false, contextIsolation: true },
  });
  try {
    await oculta.loadURL(url);
    const pdf = await oculta.webContents.printToPDF({
      printBackground: true,           // sin esto las cajas de color salen en blanco
      pageSize: 'A4',
      margins: { marginType: 'custom', top: 0.4, bottom: 0.4, left: 0.4, right: 0.4 },
    });
    fs.writeFileSync(destino.filePath, pdf);
    return { ok: true, path: destino.filePath };
  } catch (err) {
    return { ok: false, error: String((err && err.message) || err) };
  } finally {
    // Una ventana huérfana deja el proceso vivo y la aplicación no cierra.
    if (!oculta.isDestroyed()) oculta.destroy();
  }
});

const plantillaMenu = [
  ...(process.platform === 'darwin' ? [{ role: 'appMenu' }] : []),
  { role: 'fileMenu' },
  { role: 'editMenu' },
  { role: 'viewMenu' },
  { role: 'windowMenu' },
];
Menu.setApplicationMenu(Menu.buildFromTemplate(plantillaMenu));

/* ── ciclo de vida ───────────────────────────────────────────────────────── */
app.whenReady().then(async () => {
  lanzarBackend();
  try {
    await esperarBackend();
  } catch (err) {
    dialog.showErrorBox('MV AutoML Studio', String(err.message || err));
    app.quit();
    return;
  }
  crearVentana();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) crearVentana(); });
});

function apagar() {
  apagando = true;
  if (backend) {
    try { backend.kill(); } catch { /* ya muerto */ }
    backend = null;
  }
}
app.on('window-all-closed', () => { apagar(); app.quit(); });
app.on('before-quit', apagar);
process.on('exit', apagar);
