/** Panel de inicio: qué hace la plataforma y en qué estado está. */
import { t, num } from '../i18n.js';
import * as store from '../store.js';
import { el, clear, icon, stat, badge } from '../ui.js';

let nav = null;

function stepCard(n, titleKey, textKey, view) {
  return el('div', {
    class: 'card', style: 'cursor:pointer;margin:0',
    onClick: () => nav?.(view),
  },
    el('div', { class: 'row row-tight', style: 'margin-bottom:8px' },
      el('span', {
        class: 'brand-logo',
        style: 'width:24px;height:24px;font-size:12px;border-radius:6px',
        text: String(n),
      }),
      el('h3', { text: t(titleKey) })),
    el('p', { class: 'small muted mb-0', text: t(textKey) }));
}

export default {
  mount(host, { go }) {
    nav = go;
    this.host = host;
    this.render();
    store.subscribe((_, keys) => {
      if (keys.some((k) => ['datasets', 'models', 'health', 'ai'].includes(k))) this.render();
    });
  },
  refresh() { this.render(); },
  render() {
    const host = this.host;
    if (!host) return;
    const s = store.get();
    clear(host);

    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('app.name') }),
      el('p', { class: 'page-lead', text: t('app.subtitle') })));

    host.appendChild(el('div', { class: 'grid grid-4 mb-2' },
      stepCard(1, 'overview.step1_title', 'overview.step1_text', 'data'),
      stepCard(2, 'overview.step2_title', 'overview.step2_text', 'etl'),
      stepCard(3, 'overview.step3_title', 'overview.step3_text', 'model'),
      stepCard(4, 'overview.step4_title', 'overview.step4_text', 'results')));

    const engines = Object.entries(s.health?.engines || {}).filter(([, v]) => v).map(([k]) => k);
    host.appendChild(el('div', { class: 'grid grid-4 mb-2' },
      stat(t('overview.datasets_loaded'), num(s.datasets.length),
        s.datasets.length ? `${num(s.datasets.reduce((a, d) => a + (d.rows || 0), 0))} ${t('common.rows')}` : t('overview.no_limit')),
      stat(t('overview.models_trained'), num(s.models.length),
        s.models[0] ? s.models[0].model?.slice(0, 34) : '—'),
      stat(t('overview.engines'), String(engines.length), engines.join(', ') || '—'),
      stat(t('topbar.audio'), s.ai?.active ? t('topbar.ai_active') : t('topbar.ai_none'),
        s.capabilities ? `${s.capabilities.languages.join(' · ')}` : '—')));

    const card = el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h2', { text: t('overview.system') })),
      el('dl', { class: 'kv' },
        el('dt', { text: 'Python' }), el('dd', { text: s.health?.python || '—' }),
        el('dt', { text: t('common.type') }), el('dd', { text: s.health?.platform || '—' }),
        el('dt', { text: t('data.upload_formats') }),
        el('dd', { text: (s.capabilities?.file_formats || []).join(' ') || '—' }),
        el('dt', { text: t('data.sql_title') }),
        el('dd', { text: (s.capabilities?.sql_engines || []).map((e) => e.label).join(' · ') || '—' }),
        el('dt', { text: t('export.title') }),
        el('dd', { text: (s.capabilities?.export_formats || []).join(' · ').toUpperCase() || '—' })),
      el('div', { class: 'row mt-2' },
        el('button', { class: 'btn btn-primary', onClick: () => nav?.('data') }, t('overview.start'))));
    host.appendChild(card);

    host.appendChild(el('div', { class: 'note accent' }, t('model.protocol_text')));
  },
};
