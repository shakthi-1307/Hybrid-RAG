import { ChatWindow } from './ChatWindow.jsx';
import { DocumentPanel } from './DocumentPanel.jsx';
import { SessionSidebar } from './SessionSidebar.jsx';
import { useChat } from '../hooks/useChat.js';
import { useDocuments } from '../hooks/useDocuments.js';

/**
 * Mounted only when a user is signed in, so the data hooks below never fire a
 * request that would come back 401.
 */
export function Workspace({ user, onSignOut }) {
  const chat = useChat();
  const docs = useDocuments();

  return (
    <div className="layout">
      <SessionSidebar
        sessions={chat.sessions}
        activeId={chat.activeId}
        onSelect={chat.selectSession}
        onCreate={chat.startSession}
        onDelete={chat.removeSession}
      />

      <main className="main">
        <header className="app-header">
          <div>
            <h1>Hybrid RAG</h1>
            <span className="subtitle">BM25 + dense retrieval, fused with RRF</span>
          </div>
          <div className="account">
            <span className="account-email">{user.email}</span>
            <button type="button" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </header>
        <ChatWindow
          activeId={chat.activeId}
          messages={chat.messages}
          pending={chat.pending}
          error={chat.error}
          onAsk={chat.ask}
        />
      </main>

      <DocumentPanel
        documents={docs.documents}
        busy={docs.busy}
        error={docs.error}
        onUpload={docs.upload}
        onDelete={docs.remove}
      />
    </div>
  );
}
