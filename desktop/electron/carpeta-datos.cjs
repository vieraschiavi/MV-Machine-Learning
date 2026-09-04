/**
 * Dónde escribe el programa: datasets, modelos, informes y la base interna.
 *
 * Vive aparte de `main.cjs` a propósito: acá no se importa `electron`, así
 * que la decisión se puede ejecutar en una prueba de verdad
 * (`backend/tests/test_carpeta_de_datos.py`) en vez de mirarla por regex.
 *
 * Orden de resolución:
 *
 *   1. `MV_DATA_DIR`, si viene del entorno. Es el escape para poner los datos
 *      en cualquier disco sin tocar nada más.
 *   2. Una carpeta `datos` junto al programa, si ya existe y se puede escribir
 *      en ella. Es el modo portable: una copia descomprimida en `D:\MV`
 *      guarda todo en `D:\MV\datos` y no toca el disco del sistema.
 *   3. El perfil del usuario, como siempre.
 *
 * La carpeta del punto 2 **no se crea sola**, y esa es la parte que importa.
 * Una instalación normal —en `%LOCALAPPDATA%\Programs`— también puede escribir
 * en su propio directorio: si la creáramos al vuelo, toda instalación pasaría
 * a portable, y el desinstalador, que borra ese directorio, se llevaría los
 * datasets del cliente puestos. Que la carpeta exista es una señal explícita:
 * la trae el .zip portable, y en una instalación normal la crea quien quiere
 * mudar los datos a mano.
 */
'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Prueba escribiendo de verdad, no con `fs.access`: en Windows una carpeta
 * puede figurar como accesible y después fallar la escritura por la
 * virtualización de «Archivos de programa».
 */
function sePuedeEscribir(dir) {
  const testigo = path.join(dir, `.mv-escritura-${process.pid}`);
  try {
    fs.writeFileSync(testigo, '');
    return true;
  } catch {
    return false;
  } finally {
    try { fs.unlinkSync(testigo); } catch { /* no llegó a crearse */ }
  }
}

/**
 * @param {object} o
 * @param {string} o.entorno            valor de `MV_DATA_DIR` (puede venir vacío)
 * @param {boolean} o.empaquetado       `app.isPackaged`
 * @param {string} o.raizDelPrograma    carpeta que contiene el ejecutable
 * @param {string} o.perfilDelUsuario   `app.getPath('userData')`
 * @returns {string} carpeta donde el backend guarda todo
 */
function carpetaDeDatos({ entorno, empaquetado, raizDelPrograma, perfilDelUsuario }) {
  const forzada = (entorno || '').trim();
  if (forzada) return forzada;

  if (empaquetado && raizDelPrograma) {
    const alLado = path.join(raizDelPrograma, 'datos');
    // `isDirectory` y no `existsSync`: si `datos` resultara ser un archivo,
    // escribir adentro falla y hay que caer al perfil, no reventar.
    let esCarpeta = false;
    try { esCarpeta = fs.statSync(alLado).isDirectory(); } catch { /* no está */ }
    if (esCarpeta && sePuedeEscribir(alLado)) return alLado;
  }

  return path.join(perfilDelUsuario, 'data');
}

module.exports = { carpetaDeDatos, sePuedeEscribir };
