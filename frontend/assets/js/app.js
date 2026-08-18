/** Shell de la aplicación: navegación, idioma, tema y audio. */
import * as i18n from './i18n.js';
import * as audio from './audio.js';
import * as store from './store.js';
import * as api from './api.js';
import { $, $$, el, icon, clear, toast, fail, modal } from './ui.js';

import overview from './views/overview.js';
import dataView from './views/data.js';
import explore from './views/explore.js';
import etl from './views/etl.js';
import model from './views/model.js';
import results from './views/results.js';
import aiView from './views/ai.js';
import exportView from './views/export.js';
import dashboard from './views/dashboard.js';

const VIEWS = {
  overview: { icon: 'overview', section: null, mod: overview },
  data: { icon: 'data', section: 'section_data', mod: dataView },
  explore: { icon: 'explore', section: null, mod: explore },
  dashboard: { icon: 'overview', section: null, mod: dashboard },
  etl: { icon: 'etl', section: null, mod: etl },
  model: { icon: 'model', section: 'section_ml', mod: model },
  results: { icon: 'results', section: null, mod: results },
  ai: { icon: 'ai', section: 'section_system', mod: aiView },
  export: { icon: 'export', section: null, mod: exportView },
};

let currentView = null;
const mounted = new Map();

/* ── tema ────────────────────────────────────────────────────────────────── */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('mv.theme', theme);
  const btn = $('#theme-btn');
  if (btn) {
    clear(btn).appendChild(icon(theme === 'dark' ? 'sun' : 'moon'));
    btn.title = i18n.t(theme === 'dark' ? 'topbar.theme_light' : 'topbar.theme_dark');
  }
}

/* ── navegación ──────────────────────────────────────────────────────────── */
export function go(name) {
  if (!VIEWS[name]) name = 'overview';
  currentView = name;
  location.hash = `#/${name}`;
  $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  $$('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${name}`));
  $('#topbar-title').textContent = i18n.t(`nav.${name}`);
  const host = $(`#view-${name}`);
  const view = VIEWS[name].mod;
  try {
    if (!mounted.has(name)) { view.mount(host, { go }); mounted.set(name, true); }
    view.refresh?.(host);
  } catch (err) { fail(err); }
  window.scrollTo({ top: 0, behavior: 'instant' });
  $('.sidebar')?.classList.remove('open');
}

function buildNav() {
  const nav = $('#nav');
  clear(nav);
  Object.entries(VIEWS).forEach(([name, cfg]) => {
    if (cfg.section) {
      nav.appendChild(el('div', { class: 'nav-section', text: i18n.t(`nav.${cfg.section}`), 'data-i18n': `nav.${cfg.section}` }));
    }
    const btn = el('button', {
      class: 'nav-item', dataset: { view: name }, type: 'button',
      onClick: () => { audio.beep('click'); go(name); },
    }, icon(cfg.icon), el('span', { text: i18n.t(`nav.${name}`), 'data-i18n': `nav.${name}` }));
    nav.appendChild(btn);
  });
}

/* ── selector de workspace ───────────────────────────────────────────────── */
async function buildWorkspaceSelect() {
  const sel = $('#workspace-select');
  if (!sel) return;
  let list = [{ name: 'principal' }];
  try { list = (await api.get('/api/workspaces')).workspaces; } catch { /* offline */ }
  const active = api.workspaceName();
  clear(sel);
  list.forEach((w) => sel.appendChild(el('option', {
    value: w.name, selected: w.name === active,
    text: w.name + (w.datasets ? ` (${w.datasets})` : ''),
  })));
  sel.appendChild(el('option', { value: '__new__', text: i18n.t('workspace.new') }));
  if (![...sel.options].some((o) => o.selected)) sel.value = 'principal';
  sel.title = i18n.t('workspace.switch');

  sel.onchange = async () => {
    if (sel.value !== '__new__') {
      api.setWorkspace(sel.value);
      audio.beep('click');
      await store.boot();
      go(currentView || 'overview');
      return;
    }
    sel.value = api.workspaceName();
    const input = el('input', { type: 'text', placeholder: 'equipo-a' });
    const { modal } = await import('./ui.js');
    modal({
      title: i18n.t('workspace.new'),
      body: el('div', { class: 'field' },
        el('label', { text: i18n.t('workspace.name') }), input,
        el('div', { class: 'hint', text: i18n.t('workspace.name_hint') })),
      actions: [
        { label: i18n.t('common.cancel'), kind: 'ghost' },
        {
          label: i18n.t('workspace.create'), kind: 'primary',
          onClick: () => {
            api.post('/api/workspaces', { name: input.value.trim() })
              .then(async () => {
                api.setWorkspace(input.value.trim().toLowerCase());
                toast(i18n.t('workspace.created'), 'ok');
                await buildWorkspaceSelect();
                await store.boot();
                go(currentView || 'overview');
              })
              .catch((err) => fail(err));
          },
        },
      ],
    });
  };
}

/* ── barra superior ──────────────────────────────────────────────────────── */
function buildTopbar() {
  const langSel = $('#lang-select');
  clear(langSel);
  const labels = { es: 'Español', en: 'English', pt: 'Português' };
  i18n.LANGS.forEach((l) => langSel.appendChild(el('option', { value: l, text: labels[l] })));
  langSel.value = i18n.lang();
  langSel.onchange = async () => {
    await i18n.load(langSel.value);
    buildNav();
    go(currentView || 'overview');
    audio.beep('click');
  };

  $('#theme-btn').onclick = () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    audio.beep('click');
  };

  $('#menu-btn').onclick = () => $('.sidebar').classList.toggle('open');
  renderAudioButton();
  $('#audio-btn').onclick = () => { audio.toggle(); renderAudioButton(); };
  $('#audio-settings-btn').onclick = openAudioSettings;
}

function renderAudioButton() {
  const btn = $('#audio-btn');
  const on = audio.get().enabled;
  clear(btn).appendChild(icon(on ? 'volume' : 'mute'));
  btn.title = i18n.t(on ? 'topbar.audio_on' : 'topbar.audio_off');
  btn.classList.toggle('btn-primary', on);
}

function openAudioSettings() {
  const s = audio.get();
  const voices = audio.voicesFor();
  const voiceSel = el('select', {},
    ...(voices.length
      ? voices.map((v) => el('option', { value: v.voiceURI, text: `${v.name} (${v.lang})`, selected: v.voiceURI === s.voiceURI }))
      : [el('option', { value: '', text: i18n.t('audio.no_voices') })]));
  const rate = el('input', { type: 'range', min: '0.6', max: '1.6', step: '0.05', value: s.rate });
  const vol = el('input', { type: 'range', min: '0', max: '1', step: '0.05', value: s.volume });
  const narr = el('input', { type: 'checkbox', checked: s.narration });
  const snd = el('input', { type: 'checkbox', checked: s.sounds });

  const rateLabel = el('label', { text: `${i18n.t('audio.rate')}: ${s.rate.toFixed(2)}x` });
  rate.oninput = () => { rateLabel.textContent = `${i18n.t('audio.rate')}: ${Number(rate.value).toFixed(2)}x`; };

  const body = el('div', {},
    el('div', { class: 'field' }, el('label', { text: i18n.t('audio.voice') }), voiceSel),
    el('div', { class: 'field' }, rateLabel, rate),
    el('div', { class: 'field' }, el('label', { text: i18n.t('audio.volume') }), vol),
    el('div', { class: 'field' }, el('label', { class: 'switch' }, narr, el('span', { class: 'switch-track' }), el('span', { text: i18n.t('audio.narration') }))),
    el('div', { class: 'field' }, el('label', { class: 'switch' }, snd, el('span', { class: 'switch-track' }), el('span', { text: i18n.t('audio.sounds') }))),
  );

  const collect = () => ({
    voiceURI: voiceSel.value || null,
    rate: Number(rate.value),
    volume: Number(vol.value),
    narration: narr.checked,
    sounds: snd.checked,
  });

  modal({
    title: i18n.t('audio.title'),
    body,
    actions: [
      {
        label: i18n.t('audio.test'),
        onClick: () => {
          audio.set({ ...collect(), enabled: true });
          renderAudioButton();
          audio.speak(i18n.t('audio.test_phrase'), { force: true });
          return false;   // el diálogo queda abierto para seguir ajustando
        },
      },
      {
        label: i18n.t('common.save'),
        kind: 'primary',
        onClick: () => { audio.set(collect()); renderAudioButton(); },
      },
    ],
  });
}

/* ── indicador de IA ─────────────────────────────────────────────────────── */
function renderAiChip() {
  const chip = $('#ai-chip');
  const ai = store.get().ai;
  const active = ai?.active;
  clear(chip);
  chip.className = `badge ${active ? 'ok' : ''}`;
  const label = active
    ? `${i18n.t('topbar.ai_active')}: ${ai.providers.find((p) => p.provider === active)?.label || active}`
    : i18n.t('topbar.ai_none');
  chip.appendChild(document.createTextNode(label));
  chip.onclick = () => go('ai');
  chip.style.cursor = 'pointer';
}

/* ── arranque ────────────────────────────────────────────────────────────── */
async function start() {
  applyTheme(localStorage.getItem('mv.theme')
    || (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  await i18n.load(localStorage.getItem('mv.lang')
    || (navigator.language || 'es').slice(0, 2).toLowerCase());
  buildNav();
  buildTopbar();
  await buildWorkspaceSelect();
  store.subscribe((_, keys) => { if (keys.includes('ai')) renderAiChip(); });

  try {
    await store.boot();
    renderAiChip();
    $('#version').textContent = `v${store.get().health?.version || '1.0.0'}`;
  } catch (err) {
    toast(i18n.t('errors.network'), 'bad');
  }

  const initial = (location.hash.match(/#\/(\w+)/) || [])[1] || 'overview';
  go(initial);
  window.addEventListener('hashchange', () => {
    const name = (location.hash.match(/#\/(\w+)/) || [])[1];
    if (name && name !== currentView) go(name);
  });
  i18n.onChange(() => { renderAiChip(); renderAudioButton(); buildWorkspaceSelect(); });
}

start();
export { store, i18n, audio };
