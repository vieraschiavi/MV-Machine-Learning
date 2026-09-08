/**
 * Pantalla de acceso del modo servidor.
 *
 * En el escritorio no se ve nunca: Electron le pasa la credencial a la interfaz
 * por el puente seguro y nadie escribe nada. Aparece cuando el programa corre
 * en el servidor de un cliente y se abre desde el navegador de otra máquina —
 * ahí no hay puente, y el backend responde 401 hasta que alguien demuestre que
 * puede estar.
 *
 * La clave va a `sessionStorage`, no a `localStorage`: en una laptop laboral,
 * prestada o compartida, la credencial del servidor de un cliente no puede
 * sobrevivir a que se cierre la pestaña.
 */
import * as api from './api.js';
import { t } from './i18n.js';
import { el, clear } from './ui.js';

/** Pinta la pantalla y no vuelve: el arranque de la aplicación termina acá. */
export function pedirAcceso({ fallo = false } = {}) {
  const cuerpo = document.body;
  clear(cuerpo);
  cuerpo.classList.add('acceso-modo');

  const campo = el('input', {
    type: 'password', id: 'acceso-clave', autocomplete: 'off', spellcheck: 'false',
  });
  const aviso = el('p', { class: 'acceso-error', text: fallo ? t('acceso.error') : '' });
  const boton = el('button', { class: 'btn btn-primary', text: t('acceso.entrar') });

  const entrar = () => {
    const clave = campo.value.trim();
    if (!clave) { campo.focus(); return; }
    api.guardarAcceso(clave);
    // Se recarga en vez de reintentar en caliente: así el arranque entero
    // vuelve a correr con la credencial puesta, sin estados a medio armar.
    location.reload();
  };

  boton.onclick = entrar;
  campo.onkeydown = (e) => { if (e.key === 'Enter') entrar(); };

  cuerpo.appendChild(el('main', { class: 'acceso' },
    el('div', { class: 'acceso-caja' },
      el('h1', { text: t('acceso.title') }),
      el('p', { class: 'acceso-lead', text: t('acceso.lead') }),
      el('label', { for: 'acceso-clave', text: t('acceso.clave') }),
      campo,
      aviso,
      el('div', { class: 'row' }, boton),
      el('p', { class: 'hint', text: t('acceso.ayuda') }))));

  campo.focus();
}

/** True si el error que cortó el arranque es «no estás autenticado». */
export const esFaltaDeAcceso = (err) => err && err.status === 401;
