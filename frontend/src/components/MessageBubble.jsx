import { CITATION_MARKER_PATTERN, CITATION_SPLIT_PATTERN } from '../config.js';
import { CitationList } from './CitationList.jsx';

function renderWithMarkers(content) {
  return content.split(CITATION_SPLIT_PATTERN).map((part, index) =>
    CITATION_MARKER_PATTERN.test(part) ? (
      <sup key={index} className="inline-marker">
        {part}
      </sup>
    ) : (
      <span key={index}>{part}</span>
    ),
  );
}

export function MessageBubble({ message }) {
  const isUser = message.role === 'user';

  return (
    <article className={`bubble ${isUser ? 'bubble-user' : 'bubble-assistant'}`}>
      <header className="bubble-role">{isUser ? 'You' : 'Assistant'}</header>
      <div className="bubble-content">
        {isUser ? message.content : renderWithMarkers(message.content)}
      </div>
      {!isUser && <CitationList citations={message.citations} />}
    </article>
  );
}
