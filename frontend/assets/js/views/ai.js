/** Motor de IA: proveedor, clave, catálogo de modelos y verificación. */
import * as api from '../api.js';
import { t, when } from '../i18n.js';
import * as store from '../store.js';
import * as audio from '../audio.js';
import { el, clear, badge, note, fail, toast, icon } from '../ui.js';

let nav = null;

function providerCard(p, rerender) {
  const keyInput = el('input', {
    type: 'password', placeholder: p.has_key ? p.key_masked : t('ai.key_placeholder'),
    autocomplete: 'off',
  });
  const baseInput = el('input', {
    type: 'text', value: p.base_url || '', placeholder: p.default_base_url || 'https://…',
  });
  const modelSel = el('select', {},
    ...(p.models.length
      ? p.models.map((m) => el('option', { value: m, text: m, selected: m === p.model }))
      : [el('option', { value: '', text: '—' })]));

  const status = el('div', { class: 'mt-1' });
  const refreshBtn = el('button', { class: 'btn' }, icon('refresh', 15), t('ai.refresh_models'));
  const verifyBtn = el('button', { class: 'btn' }, icon('check', 15), t('ai.verify_connection'));
  const saveBtn = el('button', { class: 'btn btn-primary' }, t('common.save'));
  const activeBtn = el('button', { class: `btn ${p.is_active ? 'btn-primary' : ''}` },
    p.is_active ? t('ai.active') : t('ai.set_active'));

  const payload = (extra = {}) => ({
    provider: p.provider,
    api_key: keyInput.value || null,
    base_url: p.provider === 'custom' || baseInput.value !== p.default_base_url ? baseInput.value : null,
    model: modelSel.value || null,
    ...extra,
  });

  refreshBtn.onclick = async () => {
    refreshBtn.disabled = true;
    clear(status).appendChild(el('div', { class: 'row' }, el('span', { class: 'spinner' })));
    try {
      const r = await api.post('/api/ai/models/refresh', payload());
      clear(modelSel);
      (r.models || []).forEach((m) => modelSel.appendChild(
        el('option', { value: m, text: m, selected: m === p.model })));
      clear(status).appendChild(note(
        `${r.models?.length || 0} ${t('ai.models_found')} · ${r.source}${r.error ? ` · ${r.error}` : ''}`,
        r.ok ? 'ok' : 'warn'));
      audio.beep(r.ok ? 'success' : 'warn');
    } catch (err) { clear(status); fail(err); } finally { refreshBtn.disabled = false; }
  };

  verifyBtn.onclick = async () => {
    verifyBtn.disabled = true;
    clear(status).appendChild(el('div', { class: 'row' }, el('span', { class: 'spinner' })));
    try {
      const r = await api.post('/api/ai/verify', payload());
      clear(status).appendChild(note(
        r.ok ? `${t('ai.verify_ok')} · ${r.model} · ${r.ms} ms` : `${t('ai.verify_fail')}: ${r.error || r.detail}`,
        r.ok ? 'ok' : 'bad'));
      audio.beep(r.ok ? 'success' : 'error');
      if (r.ok) { await store.refreshAi(); rerender(); }
    } catch (err) { clear(status); fail(err); } finally { verifyBtn.disabled = false; }
  };

  saveBtn.onclick = async () => {
    try {
      await api.post('/api/ai/config', payload());
      toast(t('common.success'), 'ok');
      await store.refreshAi();
      rerender();
    } catch (err) { fail(err); }
  };

  activeBtn.onclick = async () => {
    try {
      await api.post('/api/ai/config', payload({ set_active: true }));
      await store.refreshAi();
      rerender();
      toast(`${t('topbar.ai_active')}: ${p.label}`, 'ok');
    } catch (err) { fail(err); }
  };

  return el('div', { class: 'card' },
    el('div', { class: 'card-head' },
      el('div', {},
        el('h3', { text: p.label }),
        el('div', { class: 'card-sub mono', text: p.provider })),
      p.is_active ? badge(t('ai.active'), 'accent') : null,
      badge(p.has_key ? t('ai.configured') : t('ai.not_configured'), p.has_key ? 'ok' : ''),
      p.verified_at ? badge(`${t('ai.verified')} · ${when(p.verified_at)}`, 'ok') : badge(t('ai.never_verified'))),
    el('div', { class: 'grid grid-2' },
      el('div', { class: 'field' },
        el('label', { text: t('ai.api_key') }), keyInput,
        el('div', { class: 'hint' },
          p.from_env ? 'Tomada de una variable de entorno del sistema. ' : '',
          t('ai.key_stored'),
          p.docs ? el('span', {}, ' ', el('a', { href: p.docs, target: '_blank', rel: 'noopener', text: t('ai.get_key') })) : null)),
      el('div', { class: 'field' },
        el('label', { text: t('ai.model') }), modelSel,
        el('div', { class: 'hint', text: `${p.models.length} ${t('ai.models_found')}` })),
      p.provider === 'custom' || p.base_url !== p.default_base_url
        ? el('div', { class: 'field' }, el('label', { text: t('ai.base_url') }), baseInput)
        : null),
    el('div', { class: 'row' }, refreshBtn, verifyBtn, saveBtn, el('span', { class: 'spacer' }), activeBtn),
    status);
}

export default {
  mount(host, { go }) { nav = go; this.host = host; },
  async refresh() {
    const host = this.host;
    clear(host);
    host.appendChild(el('div', { class: 'page-head' },
      el('h1', { text: t('ai.title') }),
      el('p', { class: 'page-lead', text: t('ai.lead') })));

    let ai = store.get().ai;
    try { ai = await store.refreshAi(); } catch (err) { fail(err); }

    if (!ai?.active) host.appendChild(note(t('ai.no_provider'), 'warn'));

    host.appendChild(el('div', { class: 'card' },
      el('div', { class: 'card-head' }, el('h3', { text: t('ai.uses_title') })),
      el('ul', { style: 'margin:0;padding-left:20px' },
        el('li', { text: t('ai.use1') }),
        el('li', { text: t('ai.use2') }),
        el('li', { text: t('ai.use3') }))));

    const list = el('div');
    host.appendChild(list);
    const render = () => {
      clear(list);
      (store.get().ai?.providers || []).forEach((p) => {
        list.appendChild(providerCard({ ...p, is_active: p.provider === store.get().ai?.active },
          () => render()));
      });
    };
    render();
  },
};
