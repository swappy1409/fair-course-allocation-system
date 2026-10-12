// Thin fetch wrapper. The CSRF token is kept in memory only and sent on every change.
let csrf = 'login';

export function setCsrf(token) { csrf = token || 'login'; }

export async function api(path, { method = 'GET', body, form } = {}) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (method !== 'GET') opts.headers['X-CSRF-Token'] = csrf;
  if (form) opts.body = form;
  else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error('Could not reach the server. Check your connection and try again.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Something went wrong. Please try again.';
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return data;
}

// Picks an existing session back up after a page reload.
export async function resume() {
  try {
    const s = await api('/api/session');
    setCsrf(s.csrf);
    return s;
  } catch {
    return null;
  }
}

export function logEvent(type, detail = '') {
  api('/api/event', { method: 'POST', body: { type, detail: String(detail).slice(0, 480) } }).catch(() => {});
}
