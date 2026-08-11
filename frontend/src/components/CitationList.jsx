import { useEffect, useRef, useState } from 'react';

import { CITATION_FLASH_MS } from '../config.js';
import { documentColorVars } from '../lib/documentColor.js';

export function CitationList({ citations, focusedMarker, onFocusHandled }) {
  const [expanded, setExpanded] = useState(() => new Set());
  const cardRefs = useRef(new Map());

  useEffect(() => {
    if (focusedMarker == null) return undefined;

    cardRefs.current
      .get(focusedMarker)
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    const timer = setTimeout(onFocusHandled, CITATION_FLASH_MS);
    return () => clearTimeout(timer);
  }, [focusedMarker, onFocusHandled]);

  if (citations.length === 0) return null;

  const toggle = (marker) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(marker)) next.delete(marker);
      else next.add(marker);
      return next;
    });

  return (
    <ol className="citations">
      {citations.map((citation) => {
        const isOpen = expanded.has(citation.marker);
        return (
          <li
            key={citation.chunk_id}
            ref={(node) => {
              if (node) cardRefs.current.set(citation.marker, node);
              else cardRefs.current.delete(citation.marker);
            }}
            className={`citation ${focusedMarker === citation.marker ? 'flash' : ''}`}
            style={documentColorVars(citation.document_id)}
          >
            <button
              type="button"
              className="citation-head"
              aria-expanded={isOpen}
              onClick={() => toggle(citation.marker)}
            >
              <span className="citation-marker">{citation.marker}</span>
              <span className="citation-body">
                <span className="citation-title">{citation.document_title}</span>
                <span className="citation-section">
                  {citation.section}
                  {citation.page != null ? ` · p. ${citation.page}` : ''}
                </span>
              </span>
              <span className={`citation-chevron ${isOpen ? 'open' : ''}`}>›</span>
            </button>
            {isOpen && <p className="citation-snippet">{citation.snippet}</p>}
          </li>
        );
      })}
    </ol>
  );
}