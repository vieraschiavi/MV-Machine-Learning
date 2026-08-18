/**
 * Internacionalización en tres idiomas.
 *
 * Los diccionarios viven en JSON separados y se cargan bajo demanda. Todo
 * texto visible sale de acá: no hay cadenas escritas en el HTML ni en las
 * vistas, así que agregar un cuarto idioma es agregar un archivo.
 */
const CACHE = new Map();
export const LANGS = ['es', 'en', 'pt'];

let current = 'es';
let dict = {};
const listeners = new Set();

export async function load(lang) {
  if (!LANGS.includes(lang)) lang = 'es';
  if (!CACHE.has(lang)) {
    const res = await fetch(`/assets/i18n/${lang}.json`, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`No se pudo cargar el idioma ${lang}`);
    CACHE.set(lang, await res.json());
  }
  current = lang;
  dict = CACHE.get(lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = dict.meta?.dir || 'ltr';
  localStorage.setItem('mv.lang', lang);
  apply(document);
  listeners.forEach((fn) => fn(lang, dict));
  return dict;
}

/** Traduce una clave con notación de puntos: t('nav.data'). */
export function t(key, fallback) {
  const value = key.split('.').reduce((acc, k) => (acc == null ? acc : acc[k]), dict);
  return value == null ? (fallback ?? key) : value;
}

export const lang = () => current;
export const meta = () => dict.meta || { code: current, speech: 'es-ES' };
export const speechLocale = () => dict.meta?.speech || 'es-ES';
export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

/** Aplica las traducciones a un fragmento del DOM. */
export function apply(root = document) {
  root.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  root.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  root.querySelectorAll('[data-i18n-title]').forEach((el) => {
    el.title = t(el.dataset.i18nTitle);
    el.setAttribute('aria-label', t(el.dataset.i18nTitle));
  });
}

/* ── formato numérico dependiente del idioma ─────────────────────────────── */
const LOCALES = { es: 'es-UY', en: 'en-US', pt: 'pt-BR' };
export const locale = () => LOCALES[current] || 'es-UY';

export function num(v, decimals = 0) {
  if (v == null || !isFinite(v)) return '—';
  return Number(v).toLocaleString(locale(), {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  });
}
export function pct(v, decimals = 1, alreadyPercent = false) {
  if (v == null || !isFinite(v)) return '—';
  return `${num(alreadyPercent ? v : v * 100, decimals)}%`;
}
export function dec(v, decimals = 4) {
  if (v == null || !isFinite(v)) return '—';
  return Number(v).toLocaleString(locale(), {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  });
}
export function bytes(v) {
  if (v == null || !isFinite(v)) return '—';
  const u = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let i = 0; let n = Number(v);
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i += 1; }
  return `${num(n, n >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
}
export function when(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString(locale(),
    { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
