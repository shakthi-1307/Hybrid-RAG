import { useRef } from 'react';

import { READY_STATUS } from '../config.js';

export function DocumentPanel({ documents, busy, error, onUpload, onDelete }) {
  const inputRef = useRef(null);

  const handleFile = (event) => {
    const [file] = event.target.files;
    if (file) onUpload(file);
    event.target.value = '';
  };

  const indexedChunks = documents
    .filter((doc) => doc.status === READY_STATUS)
    .reduce((total, doc) => total + doc.chunk_count, 0);

  return (
    <aside className="panel documents">
      <div className="panel-header">
        <h2>Your knowledge base</h2>
        <button
          type="button"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? 'Uploading…' : 'Add'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.md,.markdown"
          hidden
          onChange={handleFile}
        />
      </div>

      <p className="stats">
        {documents.length} documents · {indexedChunks} indexed chunks
      </p>
      {error && <p className="error">{error}</p>}

      <ul className="list">
        {documents.map((doc) => (
          <li key={doc.id} className="list-item column">
            <div className="doc-row">
              <span className="doc-title">{doc.title}</span>
              <button
                type="button"
                className="icon-button"
                aria-label="Delete document"
                onClick={() => onDelete(doc.id)}
              >
                ×
              </button>
            </div>
            <span className={`badge badge-${doc.status}`}>
              {doc.status}
              {doc.status === READY_STATUS ? ` · ${doc.chunk_count} chunks` : ''}
            </span>
            {doc.error && <span className="doc-error">{doc.error}</span>}
          </li>
        ))}
      </ul>
    </aside>
  );
}
