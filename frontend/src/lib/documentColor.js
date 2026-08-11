import {
  DOCUMENT_HUE_STEP,
  DOCUMENT_LIGHTNESS,
  DOCUMENT_SATURATION,
} from "../config.js";

/**
 * Deterministic 32-bit hash. The same document id must always produce the same
 * colour — across reloads, across sessions, and in both the document panel and
 * the citation list — or the colour stops meaning anything.
 */
function hashString(value) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function documentHue(documentId) {
  return Math.round((hashString(documentId) * DOCUMENT_HUE_STEP) % 360);
}

/**
 * Returned as a style object rather than a class, because the hue is data —
 * there is no fixed set of documents to write classes for. Components read it
 * back through `hsl(var(--doc-hue) ...)` in CSS.
 */
export function documentColorVars(documentId) {
  return {
    "--doc-hue": documentHue(documentId),
    "--doc-saturation": `${DOCUMENT_SATURATION}%`,
    "--doc-lightness": `${DOCUMENT_LIGHTNESS}%`,
  };
}
