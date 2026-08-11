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

// Mirrors the registry in backend/app/ingestion/loaders/registry.py. Used by
// the file picker and to filter what a drag-and-drop actually accepts.
export const ACCEPTED_EXTENSIONS = ['.pdf', '.md', '.markdown'];

// --- document colour coding --------------------------------------------------
// Each document gets a stable hue from its id, so a citation visibly belongs to
// a source. The golden angle spaces successive hashes far apart, which keeps
// adjacent documents from landing on near-identical colours.
export const DOCUMENT_HUE_STEP = 137.508;
export const DOCUMENT_SATURATION = 72;
export const DOCUMENT_LIGHTNESS = 62;

// --- citation interaction ----------------------------------------------------
export const CITATION_FLASH_MS = 1600;
export const SNIPPET_PREVIEW_CHARS = 180;
export const DEFAULT_SESSION_TITLE = 'New conversation';

// Mirrors PASSWORD_MIN_LENGTH in backend/app/config.py. The backend is the
// authority; this only avoids a pointless round-trip on obviously short input.
export const PASSWORD_MIN_LENGTH = 10;
// Split keeps the delimiter (capturing group); the anchored twin classifies each
// resulting fragment. Two patterns because a /g regex is stateful under .test().
export const CITATION_SPLIT_PATTERN = /(\[\d{1,2}\])/g;
export const CITATION_MARKER_PATTERN = /^\[\d{1,2}\]$/;
