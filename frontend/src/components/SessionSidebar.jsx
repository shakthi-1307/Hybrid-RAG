export function SessionSidebar({ sessions, activeId, onSelect, onCreate, onDelete }) {
  return (
    <aside className="panel sessions">
      <div className="panel-header">
        <h2>Conversations</h2>
        <button type="button" onClick={onCreate}>
          New
        </button>
      </div>
      <ul className="list">
        {sessions.map((session) => (
          <li
            key={session.id}
            className={`list-item ${session.id === activeId ? 'active' : ''}`}
          >
            <button
              type="button"
              className="list-label"
              onClick={() => onSelect(session.id)}
            >
              {session.title}
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label="Delete conversation"
              onClick={() => onDelete(session.id)}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
