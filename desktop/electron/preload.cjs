/**
 * Puente seguro entre la interfaz y el escritorio.
 *
 * La interfaz corre con contextIsolation y sandbox: no ve Node. Lo único que
 * recibe es este objeto: el token de sesión para autenticar contra el backend
 * y el dato de que corre dentro del escritorio.
 */
const { contextBridge, ipcRenderer } = require('electron');

const tokenArg = process.argv.find((a) => a.startsWith('--mv-token='));

contextBridge.exposeInMainWorld('mvDesktop', {
  token: tokenArg ? tokenArg.slice('--mv-token='.length) : null,
  platform: process.platform,

  /**
   * Guarda como PDF un documento que sirve el backend local (hoy, la
   * bitácora). En el navegador esto se hace con el cuadro de impresión; acá
   * se guarda directo, sin pasar por una impresora.
   *
   * Se expone la función, no el canal: la interfaz no puede elegir a qué
   * canal le habla, y el proceso principal valida igual la dirección que
   * recibe antes de abrirla.
   */
  guardarPDF: (url, nombre) => ipcRenderer.invoke('mv:guardar-pdf', { url, nombre }),
});
