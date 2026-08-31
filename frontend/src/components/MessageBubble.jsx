import { useCallback, useState } from 'react';

import {
  CITATION_MARKER_PATTERN,
  CITATION_SPLIT_PATTERN,
  SNIPPET_PREVIEW_CHARS,
} from '../config.js';
import { documentColorVars } from '../lib/documentColor.js';
import { CitationList } from './CitationList.jsx';

export function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const [focusedMarker, setFocusedMarker] = useState(null);
  const clearFocus = useCallback(() => setFocusedMarker(null), []);

  const byMarker = new Map(
    message.citations.map((citation) => [citation.marker, citation]),
  );

  const renderAnswer = () =>
    message.content.split(CITATION_SPLIT_PATTERN).map((part, index) => {
      if (!CITATION_MARKER_PATTERN.test(part)) {
        return <span key={index}>{part}</span>;
      }

      const marker = Number(part.slice(1, -1));
      const citation = byMarker.get(marker);

      // The backend drops markers pointing outside the supplied context, so a
      // marker can survive in the text with no citation behind it. Showing it
      // struck through is more honest than hiding the model's mistake.
      if (!citation) {
        return (
          <span key={index} className="inline-marker orphan" title="No such source">
            {part}
          </span>
        );
      }

      return (
        <button
          key={index}
          type="button"
          className="inline-marker"
          style={documentColorVars(citation.document_id)}
          onClick={() => setFocusedMarker(marker)}
          aria-label={`Jump to source ${marker}, ${citation.document_title}`}
        >
          {marker}
          <span className="marker-tooltip" role="tooltip">
            <strong>{citation.document_title}</strong>
            <em>{citation.section}</em>
            {citation.snippet.slice(0, SNIPPET_PREVIEW_CHARS)}…
          </span>
        </button>
      );
    });

  // While tokens are still arriving the text is rendered raw. Markers cannot
  // be resolved yet — validation needs the finished answer, and "[1" is not
  // yet "[12]" — so treating them as citations mid-stream would flash every
  // marker from broken to valid as the reply completes.
  const renderBody = () => {
    if (isUser) return message.content;
    if (message.streaming) {
      return (
        <>
          {message.content}
          <span className="cursor" aria-hidden="true" />
        </>
      );
    }
    return renderAnswer();
  };

  return (
    <article className={`bubble ${isUser ? 'bubble-user' : 'bubble-assistant'}`}>
      <header className="bubble-role">{isUser ? 'You' : 'Assistant'}</header>
      <div className="bubble-content">{renderBody()}</div>
      {!isUser && !message.streaming && (
        <CitationList
          citations={message.citations}
          focusedMarker={focusedMarker}
          onFocusHandled={clearFocus}
        />
      )}
    </article>
  );
}