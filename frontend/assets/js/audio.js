/**
 * Sistema de audio.
 *
 * Tres piezas:
 *   1. narración de resultados con la voz del idioma activo (síntesis del
 *      navegador, sin servicio externo ni clave);
 *   2. señales sonoras de la interfaz, sintetizadas con WebAudio — no hay
 *      archivos de sonido que descargar;
 *   3. dictado por voz para escribir el objetivo sin teclado.
 *
 * Todo es opcional y arranca apagado: el audio se activa sólo si el usuario
 * lo pide, y el estado queda guardado en el equipo.
 */
import { speechLocale, t } from './i18n.js';

const KEY = 'mv.audio';
const state = {
  enabled: false, sounds: true, narration: true,
  rate: 1.0, volume: 0.9, voiceURI: null,
};
Object.assign(state, JSON.parse(localStorage.getItem(KEY) || '{}'));

const listeners = new Set();
let ctx = null;
let voices = [];

function persist() {
  localStorage.setItem(KEY, JSON.stringify(state));
  listeners.forEach((fn) => fn({ ...state }));
}

export const get = () => ({ ...state });
export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

export function set(patch) {
  Object.assign(state, patch);
  if (!state.enabled) stop();
  persist();
}

export function toggle() {
  set({ enabled: !state.enabled });
  if (state.enabled) beep('on');
  return state.enabled;
}

/* ── señales sonoras ─────────────────────────────────────────────────────── */
const TONES = {
  on:      [[660, 0.06], [880, 0.09]],
  click:   [[520, 0.03]],
  success: [[587, 0.07], [784, 0.11]],
  error:   [[300, 0.10], [220, 0.16]],
  warn:    [[440, 0.07], [392, 0.10]],
  done:    [[523, 0.06], [659, 0.06], [784, 0.13]],
  start:   [[392, 0.05], [523, 0.07]],
};

/** Sintetiza un tono corto. Sin assets: la señal se genera en el momento. */
export function beep(kind = 'click') {
  if (!state.enabled || !state.sounds) return;
  const seq = TONES[kind] || TONES.click;
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === 'suspended') ctx.resume();
    let at = ctx.currentTime;
    seq.forEach(([freq, dur]) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, at);
      const peak = 0.10 * state.volume;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(peak, at + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + dur);
      osc.connect(gain).connect(ctx.destination);
      osc.start(at);
      osc.stop(at + dur + 0.02);
      at += dur * 0.85;
    });
  } catch { /* el audio nunca debe romper la interfaz */ }
}

/* ── voces ───────────────────────────────────────────────────────────────── */
export function refreshVoices() {
  if (!('speechSynthesis' in window)) return [];
  voices = window.speechSynthesis.getVoices() || [];
  return voices;
}
if ('speechSynthesis' in window) {
  refreshVoices();
  window.speechSynthesis.onvoiceschanged = () => { refreshVoices(); listeners.forEach((fn) => fn({ ...state })); };
}

/** Voces compatibles con el idioma activo (por ejemplo es-*, en-*, pt-*). */
export function voicesFor(localeCode = speechLocale()) {
  const base = localeCode.split('-')[0].toLowerCase();
  if (!voices.length) refreshVoices();
  const matching = voices.filter((v) => v.lang.toLowerCase().startsWith(base));
  return matching.length ? matching : voices;
}

function pickVoice() {
  const list = voicesFor();
  if (!list.length) return null;
  return list.find((v) => v.voiceURI === state.voiceURI)
      || list.find((v) => v.lang.toLowerCase() === speechLocale().toLowerCase())
      || list.find((v) => v.localService) || list[0];
}

/* ── narración ───────────────────────────────────────────────────────────── */
let speaking = false;
export const isSpeaking = () => speaking;

export function speak(text, { force = false } = {}) {
  if (!('speechSynthesis' in window)) return false;
  if (!force && (!state.enabled || !state.narration)) return false;
  const clean = String(text || '')
    .replace(/[«»"]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!clean) return false;
  stop();
  // Los motores del navegador cortan textos muy largos: se parte en frases.
  const chunks = clean.match(/[^.!?]+[.!?]*/g) || [clean];
  const groups = [];
  let buf = '';
  chunks.forEach((c) => {
    if ((buf + c).length > 220) { groups.push(buf.trim()); buf = c; } else { buf += c; }
  });
  if (buf.trim()) groups.push(buf.trim());

  const voice = pickVoice();
  speaking = true;
  groups.forEach((part, i) => {
    const u = new SpeechSynthesisUtterance(part);
    u.lang = speechLocale();
    if (voice) u.voice = voice;
    u.rate = state.rate;
    u.volume = state.volume;
    u.pitch = 1;
    if (i === groups.length - 1) {
      u.onend = () => { speaking = false; listeners.forEach((fn) => fn({ ...state })); };
      u.onerror = () => { speaking = false; };
    }
    window.speechSynthesis.speak(u);
  });
  listeners.forEach((fn) => fn({ ...state }));
  return true;
}

export function stop() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  speaking = false;
}

export const supported = () => 'speechSynthesis' in window;

/* ── dictado ─────────────────────────────────────────────────────────────── */
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
export const dictationSupported = () => Boolean(Recognition);

export function dictate({ onResult, onEnd, onError } = {}) {
  if (!Recognition) { onError?.(t('audio.voice_unsupported')); return null; }
  const rec = new Recognition();
  rec.lang = speechLocale();
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;
  rec.onresult = (e) => {
    let text = '';
    for (let i = e.resultIndex; i < e.results.length; i += 1) text += e.results[i][0].transcript;
    onResult?.(text, e.results[e.results.length - 1].isFinal);
  };
  rec.onerror = (e) => onError?.(e.error);
  rec.onend = () => onEnd?.();
  try { rec.start(); beep('start'); } catch { onError?.('start'); }
  return rec;
}
