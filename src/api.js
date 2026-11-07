const base = (import.meta.env?.VITE_API_URL || '').replace(/\/$/, '');
let tokens = null;
let version = 0;
let refreshJob = null;
const authListeners = new Set();
try {
  const saved = JSON.parse(sessionStorage.getItem('worktrack-auth') || 'null');
  if (
    typeof saved?.access === 'string' &&
    saved.access &&
    typeof saved?.refresh === 'string' &&
    saved.refresh
  )
    tokens = saved;
  else sessionStorage.removeItem('worktrack-auth');
} catch {
  sessionStorage.removeItem('worktrack-auth');
}
export class APIError extends Error {
  constructor(message, status = 0, retryAfter = null, details = null) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.retryAfter = retryAfter;
    this.details = details;
  }
}
export function hasAuth() {
  return Boolean(tokens);
}
export function onAuthCleared(listener) {
  authListeners.add(listener);
  return () => authListeners.delete(listener);
}
export function clearAuth(reason = 'logout') {
  version += 1;
  tokens = null;
  sessionStorage.removeItem('worktrack-auth');
  for (const listener of authListeners) listener(reason);
}
function save(value) {
  tokens = value;
  sessionStorage.setItem('worktrack-auth', JSON.stringify(value));
}
function cancelled() {
  return new DOMException('Request belongs to an ended session.', 'AbortError');
}
function checkSession(expected, signal) {
  if (expected !== version || signal?.aborted) throw cancelled();
}
async function fetchResponse(path, options) {
  try {
    return await fetch((path.startsWith('/desktop/') ? '' : base) + path, options);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new APIError('Сервертэй холбогдож чадсангүй. Холболт болон backend серверээ шалгана уу.');
  }
}
function errorMessage(data) {
  if (typeof data?.detail === 'string') return data.detail;
  if (typeof data === 'string') return data;
  if (Array.isArray(data)) return data.map(errorMessage).join(' ');
  if (data && typeof data === 'object')
    return Object.entries(data)
      .map(([key, value]) => `${key}: ${errorMessage(value)}`)
      .join('; ');
  return 'Хүсэлтийг гүйцэтгэж чадсангүй.';
}
async function readResponse(response) {
  if (response.status === 204) return null;
  let data;
  try {
    data = await response.json();
  } catch {
    throw new APIError(
      response.status >= 500
        ? 'Backend сервертэй холбогдож чадсангүй. Django сервер 8000 порт дээр ажиллаж байгаа эсэхийг шалгана уу.'
        : 'Серверээс буруу форматтай хариу ирлээ. API хаягийг шалгана уу.',
      response.status,
    );
  }
  if (!response.ok) {
    const wait = Number(response.headers.get('Retry-After')) || null;
    const message =
      response.status === 429 && wait
        ? `Хэт олон оролдлого хийсэн байна. ${wait} секунд хүлээгээд дахин оролдоно уу.`
        : errorMessage(data);
    throw new APIError(message, response.status, wait, data);
  }
  return data;
}
function refreshSession(expected) {
  if (refreshJob?.version === expected) return refreshJob.promise;
  const job = { version: expected, promise: null };
  job.promise = (async () => {
    const refresh = tokens.refresh;
    const response = await fetchResponse('/api/auth/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    });
    checkSession(expected);
    if (response.status === 400 || response.status === 401) {
      clearAuth('expired');
      throw new APIError('Нэвтрэх хугацаа дууссан. Дахин нэвтэрнэ үү.', 401);
    }
    const refreshed = await readResponse(response);
    checkSession(expected);
    if (typeof refreshed?.access !== 'string' || !refreshed.access)
      throw new APIError('Access token серверээс ирсэнгүй.', response.status);
    save({ ...tokens, ...refreshed });
  })().finally(() => {
    if (refreshJob === job) refreshJob = null;
  });
  refreshJob = job;
  return job.promise;
}
export async function api(path, options = {}, retry = true) {
  const expected = version;
  checkSession(expected, options.signal);
  const response = await fetchResponse(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(tokens ? { Authorization: `Bearer ${tokens.access}` } : {}),
      ...options.headers,
    },
  });
  checkSession(expected, options.signal);
  if (response.status === 401 && tokens && retry) {
    await refreshSession(expected);
    checkSession(expected, options.signal);
    return api(path, options, false);
  }
  if (response.status === 401 && tokens && path !== '/api/auth/login/') clearAuth('expired');
  const data = await readResponse(response);
  checkSession(expected, options.signal);
  return data;
}
export async function login(username, password) {
  // A newer login attempt or logout must invalidate this attempt's response.
  version += 1;
  tokens = null;
  sessionStorage.removeItem('worktrack-auth');
  const expected = version;
  const data = await api(
    '/api/auth/login/',
    { method: 'POST', body: JSON.stringify({ username, password }) },
    false,
  );
  checkSession(expected);
  if (
    typeof data?.access !== 'string' ||
    !data.access ||
    typeof data?.refresh !== 'string' ||
    !data.refresh
  )
    throw new APIError('Login token серверээс ирсэнгүй.');
  save(data);
}

export async function desktop(action, options = {}) {
  try {
    return await api(`/desktop/${action}/`, {
      ...options,
      headers: { ...options.headers, 'X-WorkTrack-Desktop': '1' },
    });
  } catch (error) {
    if (
      error.name !== 'AbortError' &&
      (!error.status || error.status === 200 || error.status === 404 || error.status >= 500)
    )
      throw new APIError(
        'WorkTrack.app эсвэл Start WorkTrack.command-аа нээгээд дахин холбоно уу.',
        error.status,
      );
    throw error;
  }
}

export async function downloadReport(path, options = {}, retry = true) {
  const expected = version;
  checkSession(expected, options.signal);
  const response = await fetchResponse(path, {
    ...options,
    headers: { ...(tokens ? { Authorization: `Bearer ${tokens.access}` } : {}) },
  });
  checkSession(expected, options.signal);
  if (response.status === 401 && tokens && retry) {
    await refreshSession(expected);
    checkSession(expected, options.signal);
    return downloadReport(path, options, false);
  }
  if (response.status === 401 && tokens) clearAuth('expired');
  if (!response.ok) await readResponse(response);
  const blob = await response.blob();
  checkSession(expected, options.signal);
  return blob;
}
export async function logout() {
  if (tokens) {
    try {
      await api('/api/auth/logout/', {
        method: 'POST',
        body: JSON.stringify({ refresh: tokens.refresh }),
      });
    } catch (error) {
      // This endpoint returns 400 for an expired/already-revoked refresh.
      // It cannot refresh the session anymore, so a local exit is still valid.
      if (error.status !== 400) throw error;
    }
  }
  clearAuth();
}

export async function list(path, options = {}) {
  const rows = [];
  while (path) {
    const data = await api(path, options);
    if (Array.isArray(data)) return data;
    rows.push(...data.results);
    path = data.next
      ? new URL(data.next, window.location.origin).pathname +
        new URL(data.next, window.location.origin).search
      : null;
  }
  return rows;
}
