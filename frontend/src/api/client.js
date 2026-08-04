import { API_BASE_URL } from '../config.js';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    // The session token lives in an httpOnly cookie, so every call must opt in
    // to sending credentials cross-origin.
    credentials: 'include',
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed with status ${response.status}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function jsonBody(payload) {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  };
}

export const api = {
  register: (email, password) =>
    request('/auth/register', jsonBody({ email, password })),
  login: (email, password) => request('/auth/login', jsonBody({ email, password })),
  logout: () => request('/auth/logout', { method: 'POST' }),
  getCurrentUser: () => request('/auth/me'),

  listDocuments: () => request('/documents'),
  uploadDocument: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/documents', { method: 'POST', body: form });
  },
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),

  listSessions: () => request('/chat/sessions'),
  createSession: (title) => request('/chat/sessions', jsonBody({ title })),
  deleteSession: (id) => request(`/chat/sessions/${id}`, { method: 'DELETE' }),
  listMessages: (id) => request(`/chat/sessions/${id}/messages`),
  sendQuery: (id, question) =>
    request(`/chat/sessions/${id}/query`, jsonBody({ question })),
};
