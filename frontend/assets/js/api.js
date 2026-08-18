/** Cliente HTTP de la API. Todo error del servidor llega acá con mensaje legible. */

/** Workspace activo: viaja en cada request y aísla datasets, modelos y archivos. */
export const workspaceName = () => localStorage.getItem('mv.workspace') || 'principal';
export function setWorkspace(name) {
  localStorage.setItem('mv.workspace', name || 'principal');
}
/** Anexa el workspace a URLs que no pueden mandar encabezados (SSE, descargas). */
export function withWorkspace(url) {
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}workspace=${encodeURIComponent(workspaceName())}`;
}

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

async function request(method, path, body, options = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: {
        'X-Workspace': workspaceName(),
        ...(body instanceof FormData || body == null ? {} : { 'Content-Type': 'application/json' }),
      },
      body: body == null ? undefined : (body instanceof FormData ? body : JSON.stringify(body)),
      signal: options.signal,
    });
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw new ApiError('NETWORK', 0, null);
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) {
    const detail = data?.detail ?? data?.message ?? `HTTP ${res.status}`;
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), res.status, data);
  }
  return data;
}

export const get = (p) => request('GET', p);
export const post = (p, b) => request('POST', p, b);
export const del = (p) => request('DELETE', p);

/* ── subida por streaming: sin tope de tamaño ────────────────────────────── */
export function uploadFile(file, { name, onProgress } = {}) {
  const params = new URLSearchParams({ filename: file.name });
  if (name) params.set('name', name);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/datasets/upload-stream?${params}`);
    xhr.setRequestHeader('X-Workspace', workspaceName());
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total, e.loaded, e.total);
    };
    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { data = { detail: xhr.responseText }; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(data?.detail || `HTTP ${xhr.status}`, xhr.status, data));
    };
    xhr.onerror = () => reject(new ApiError('NETWORK', 0, null));
    xhr.send(file);
  });
}

/* ── seguimiento de trabajos ─────────────────────────────────────────────── */
/**
 * Sigue un job por server-sent events y resuelve con su resultado.
 * Si el navegador o un proxy corta el stream, cae a sondeo periódico:
 * el entrenamiento nunca queda huérfano por un problema de transporte.
 */
export function followJob(jobId, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let source = null;
    let pollTimer = null;

    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      if (source) source.close();
      if (pollTimer) clearInterval(pollTimer);
      fn(value);
    };

    const handle = (job) => {
      if (!job) return;
      if (onProgress) onProgress(job);
      if (job.status === 'terminado') finish(resolve, job.result);
      else if (job.status === 'error') {
        finish(reject, new ApiError(job.error?.message || 'Error en el trabajo', 500, job.error));
      } else if (job.status === 'cancelado') {
        finish(reject, new ApiError('CANCELLED', 499, job));
      }
    };

    const poll = async () => {
      try { handle(await get(`/api/jobs/${jobId}`)); } catch { /* se reintenta */ }
    };

    try {
      source = new EventSource(withWorkspace(`/api/jobs/${jobId}/stream`));
      source.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch { /* ignorado */ } };
      source.onerror = () => {
        if (settled) return;
        source.close();
        source = null;
        if (!pollTimer) { pollTimer = setInterval(poll, 1500); poll(); }
      };
    } catch {
      pollTimer = setInterval(poll, 1500);
      poll();
    }
  });
}

export async function runJob(path, body, onProgress) {
  const job = await post(path, body);
  if (!job?.id) return job;
  return followJob(job.id, { onProgress });
}
