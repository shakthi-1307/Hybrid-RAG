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

/**
 * Consume a Server-Sent Event stream.
 *
 * fetch + ReadableStream rather than EventSource: EventSource cannot issue a
 * POST and cannot send a request body, and the question has to go in one.
 *
 * `onEvent` is called with ({ event, data }) for each frame. Frames are only
 * dispatched once terminated by a blank line — a chunk boundary can land in
 * the middle of a frame, and parsing a half-received one would drop tokens.
 */
async function stream(path, payload, onEvent, signal) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'include',
    signal,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed with status ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf('\n\n');

      let eventName = 'message';
      const dataLines = [];
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
        // Anything else is a comment or a field we do not use (`: keepalive`).
      }
      if (dataLines.length === 0) continue;

      try {
        onEvent({ event: eventName, data: JSON.parse(dataLines.join('\n')) });
      } catch {
        // A malformed frame must not abort a stream that is otherwise fine.
      }
    }
  }
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
  streamQuery: (id, question, onEvent, signal) =>
    stream(`/chat/sessions/${id}/query/stream`, { question }, onEvent, signal),
};
