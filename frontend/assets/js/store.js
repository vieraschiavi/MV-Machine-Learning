/** Estado compartido entre vistas. Cambios observables, sin framework. */
import * as api from './api.js';

const state = {
  health: null,
  capabilities: null,
  datasets: [],
  datasetId: localStorage.getItem('mv.dataset') || null,
  profile: null,
  target: localStorage.getItem('mv.target') || null,
  task: null,
  etlPlan: null,
  etlResult: null,
  models: [],
  modelId: localStorage.getItem('mv.model') || null,
  report: null,
  ai: null,
};

const listeners = new Set();
export const get = () => state;
export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }
function emit(keys) { listeners.forEach((fn) => fn(state, keys)); }

export function set(patch) {
  Object.assign(state, patch);
  if ('datasetId' in patch) {
    if (patch.datasetId) localStorage.setItem('mv.dataset', patch.datasetId);
    else localStorage.removeItem('mv.dataset');
    // el perfil y el plan pertenecen al dataset anterior: se descartan
    if (!('profile' in patch)) state.profile = null;
    if (!('etlPlan' in patch)) state.etlPlan = null;
  }
  if ('target' in patch) {
    if (patch.target) localStorage.setItem('mv.target', patch.target);
    else localStorage.removeItem('mv.target');
  }
  if ('modelId' in patch) {
    if (patch.modelId) localStorage.setItem('mv.model', patch.modelId);
    else localStorage.removeItem('mv.model');
  }
  emit(Object.keys(patch));
}

export const dataset = () => state.datasets.find((d) => d.id === state.datasetId) || null;
export const columns = () => (dataset()?.columns || []).map((c) => c.name);

export async function refreshDatasets() {
  const { datasets } = await api.get('/api/datasets');
  const ids = new Set(datasets.map((d) => d.id));
  set({ datasets, datasetId: ids.has(state.datasetId) ? state.datasetId : (datasets[0]?.id || null) });
  return datasets;
}

export async function refreshModels() {
  const { models } = await api.get('/api/automl/models');
  const ids = new Set(models.map((m) => m.id));
  set({ models, modelId: ids.has(state.modelId) ? state.modelId : (models[0]?.id || null) });
  return models;
}

export async function loadProfile(force = false) {
  if (!state.datasetId) return null;
  if (state.profile && state.profile.dataset_id === state.datasetId && !force) return state.profile;
  const profile = await api.get(`/api/datasets/${state.datasetId}/profile`);
  set({ profile });
  return profile;
}

export async function loadReport(modelId = state.modelId) {
  if (!modelId) return null;
  const card = await api.get(`/api/automl/models/${modelId}`);
  set({ report: card.report, modelId });
  return card.report;
}

export async function refreshAi() {
  const ai = await api.get('/api/ai/status');
  set({ ai });
  return ai;
}

export async function boot() {
  const [health, capabilities] = await Promise.all([
    api.get('/api/health'), api.get('/api/capabilities'),
  ]);
  set({ health, capabilities });
  await Promise.allSettled([refreshDatasets(), refreshModels(), refreshAi()]);
}
