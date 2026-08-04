// Every frontend constant is declared here once.
//
// Relative by default: nginx (prod) and the Vite dev server both proxy /api to
// the backend, so the browser only ever talks to one origin. That means no
// CORS preflight and a first-party session cookie.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

// Documents ingest in the background; poll until nothing is pending.
export const INGESTION_POLL_INTERVAL_MS = 3000;

export const PENDING_STATUSES = ['pending', 'processing'];
export const READY_STATUS = 'ready';
export const DEFAULT_SESSION_TITLE = 'New conversation';

// Mirrors PASSWORD_MIN_LENGTH in backend/app/config.py. The backend is the
// authority; this only avoids a pointless round-trip on obviously short input.
export const PASSWORD_MIN_LENGTH = 10;
// Split keeps the delimiter (capturing group); the anchored twin classifies each
// resulting fragment. Two patterns because a /g regex is stateful under .test().
export const CITATION_SPLIT_PATTERN = /(\[\d{1,2}\])/g;
export const CITATION_MARKER_PATTERN = /^\[\d{1,2}\]$/;
