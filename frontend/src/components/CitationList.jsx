export function CitationList({ citations }) {
  if (citations.length === 0) return null;

  return (
    <ol className="citations">
      {citations.map((citation) => (
        <li key={citation.chunk_id} className="citation">
          <span className="citation-marker">[{citation.marker}]</span>
          <div className="citation-body">
            <span className="citation-title">{citation.document_title}</span>
            <span className="citation-section">
              {citation.section}
              {citation.page !== null && citation.page !== undefined
                ? ` · p. ${citation.page}`
                : ''}
            </span>
            <p className="citation-snippet">{citation.snippet}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
