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
const { app, BrowserWindow, Menu, dialog, shell } = require('electron');
const { spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');

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
  const datos = path.join(app.getPath('userData'), 'data');
  fs.mkdirSync(datos, { recursive: true });

  backend = spawn(cmd, args, {
    cwd: app.isPackaged ? path.dirname(cmd) : recursos(),
    env: {
      ...process.env,
      MV_HOST: '127.0.0.1',
      MV_PORT: String(PORT),
      MV_API_TOKEN: TOKEN,
      MV_DATA_DIR: datos,               // datos en el perfil del usuario, nunca en C:\ fijo
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
