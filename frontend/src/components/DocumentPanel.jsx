import { useRef, useState } from 'react';

import { ACCEPTED_EXTENSIONS, PENDING_STATUSES, READY_STATUS } from '../config.js';
import { documentColorVars } from '../lib/documentColor.js';

function isAccepted(file) {
  return ACCEPTED_EXTENSIONS.some((extension) =>
    file.name.toLowerCase().endsWith(extension),
  );
}

export function DocumentPanel({ documents, uploading, busy, error, onUpload, onDelete }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  // dragenter/dragleave fire for every child element, so a boolean flickers.
  // Counting depth is what makes the highlight stable.
  const dragDepth = useRef(0);

  const handlePicked = (event) => {
    onUpload(event.target.files);
    event.target.value = '';
  };

  const handleDrop = (event) => {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    onUpload(Array.from(event.dataTransfer.files).filter(isAccepted));
  };

  const indexedChunks = documents
    .filter((doc) => doc.status === READY_STATUS)
    .reduce((total, doc) => total + doc.chunk_count, 0);

  return (
    <aside
      className={`panel documents ${dragging ? 'dropping' : ''}`}
      onDragEnter={(event) => {
        event.preventDefault();
        dragDepth.current += 1;
        setDragging(true);
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        dragDepth.current -= 1;
        if (dragDepth.current <= 0) {
          dragDepth.current = 0;
          setDragging(false);
        }
      }}
      onDragOver={(event) => event.preventDefault()}
      onDrop={handleDrop}
    >
      {dragging && (
        <div className="dropzone-overlay">
          <span className="dropzone-icon">↓</span>
          <strong>Drop to ingest</strong>
          <span className="hint">{ACCEPTED_EXTENSIONS.join('  ·  ')}</span>
        </div>
      )}

      <div className="panel-header">
        <h2>Your knowledge base</h2>
        <button type="button" disabled={busy} onClick={() => inputRef.current?.click()}>
          {busy ? 'Uploading…' : 'Add'}
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(',')}
          hidden
          onChange={handlePicked}
        />
      </div>

      <p className="stats">
        <span className="stat-value">{documents.length}</span> documents ·{' '}
        <span className="stat-value">{indexedChunks}</span> indexed chunks
      </p>
      {error && <p className="error">{error}</p>}

      {uploading.length > 0 && (
        <ul className="upload-queue">
          {uploading.map((name) => (
            <li key={name} className="upload-item">
              <span className="spinner" aria-hidden="true" />
              {name}
            </li>
          ))}
        </ul>
      )}

      <ul className="list">
        {documents.map((doc) => {
          const working = PENDING_STATUSES.includes(doc.status);
          return (
            <li
              key={doc.id}
              className="list-item column doc-card"
              style={documentColorVars(doc.id)}
            >
              <div className="doc-row">
                <span className="doc-dot" aria-hidden="true" />
                <span className="doc-title" title={doc.filename}>
                  {doc.title}
                </span>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Delete ${doc.title}`}
                  onClick={() => onDelete(doc.id)}
                >
                  ×
                </button>
              </div>

              <span className={`badge badge-${doc.status}`}>
                {doc.status}
                {doc.status === READY_STATUS ? ` · ${doc.chunk_count} chunks` : ''}
              </span>

              {/* Indeterminate: ingestion reports completion, not percentage. */}
              {working && <span className="doc-progress" aria-hidden="true" />}
              {doc.error && <span className="doc-error">{doc.error}</span>}
            </li>
          );
        })}
      </ul>

      {documents.length === 0 && uploading.length === 0 && (
        <p className="empty-hint">
          Drop a PDF or Markdown file here, or use Add.
        </p>
      )}
    </aside>
  );
}