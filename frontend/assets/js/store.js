/** Estado compartido entre vistas. Cambios observables, sin framework. */
import * as api from './api.js';

const state = {
  health: null,
  capabilities: null,
  datasets: [],
  // El dataset activo lo decide el servidor, por workspace (GET /api/datasets/active):
  // guardado en el navegador, cada pestaña terminaba con su propia elección y el
  // workspace nuevo heredaba la del anterior.
  datasetId: null,
  datasetOrigen: null,
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
    // el perfil y el plan pertenecen al dataset anterior: se descartan
    if (!('profile' in patch)) state.profile = null;
    if (!('etlPlan' in patch)) state.etlPlan = null;
    // y el objetivo también, si el dataset nuevo no tiene esa columna
    if (!('target' in patch) && state.target && !columns().includes(state.target)) {
      state.target = null;
      localStorage.removeItem('mv.target');
    }
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

/** Aplica la respuesta del resolver del servidor (`/api/datasets/active`). */
function aplicarActivo(activo) {
  set({ datasetId: activo?.id || null, datasetOrigen: activo?.origen || null });
}

export async function refreshDatasets() {
  const [{ datasets }, activo] = await Promise.all([
    api.get('/api/datasets'), api.get('/api/datasets/active')]);
  state.datasets = datasets;
  aplicarActivo(activo);
  emit(['datasets']);
  return datasets;
}

/**
 * Elegir el dataset de TODAS las pestañas. Es la única puerta: cargar un
 * archivo, extraer por SQL, ejecutar el ETL o elegirlo en cualquier selector
 * pasa por acá, y el servidor lo recuerda para el workspace.
 */
export async function elegirDataset(id) {
  if (!id || id === state.datasetId) return;
  set({ datasetId: id, datasetOrigen: 'elegido' });   // la interfaz responde ya
  try { aplicarActivo(await api.put('/api/datasets/active', { dataset_id: id })); }
  catch { await refreshDatasets(); }                  // p. ej. lo borraron en otra pestaña
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
