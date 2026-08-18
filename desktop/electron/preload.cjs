/**
 * Puente seguro entre la interfaz y el escritorio.
 *
 * La interfaz corre con contextIsolation y sandbox: no ve Node. Lo único que
 * recibe es este objeto: el token de sesión para autenticar contra el backend
 * y el dato de que corre dentro del escritorio.
 */
const { contextBridge } = require('electron');

const tokenArg = process.argv.find((a) => a.startsWith('--mv-token='));

contextBridge.exposeInMainWorld('mvDesktop', {
  token: tokenArg ? tokenArg.slice('--mv-token='.length) : null,
  platform: process.platform,
});
