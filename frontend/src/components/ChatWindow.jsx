import { useEffect, useRef } from 'react';

import { Composer } from './Composer.jsx';
import { MessageBubble } from './MessageBubble.jsx';

export function ChatWindow({ activeId, messages, pending, error, onAsk }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pending]);

  if (!activeId) {
    return (
      <section className="chat empty">
        <p>Start a conversation to query your indexed documents.</p>
      </section>
    );
  }

  return (
    <section className="chat">
      <div className="transcript">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {pending && <div className="thinking">Retrieving and grounding…</div>}
        <div ref={endRef} />
      </div>
      {error && <p className="error">{error}</p>}
      <Composer disabled={pending} onSubmit={onAsk} />
    </section>
  );
}
