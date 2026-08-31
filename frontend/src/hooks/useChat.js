import { useCallback, useEffect, useState } from 'react';

import { api } from '../api/client.js';
import { DEFAULT_SESSION_TITLE } from '../config.js';

export function useChat() {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const loadSessions = useCallback(async () => {
    const list = await api.listSessions();
    setSessions(list);
    return list;
  }, []);

  useEffect(() => {
    loadSessions().catch((err) => setError(err.message));
  }, [loadSessions]);

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    api
      .listMessages(activeId)
      .then(setMessages)
      .catch((err) => setError(err.message));
  }, [activeId]);

  const startSession = useCallback(async () => {
    try {
      const created = await api.createSession(DEFAULT_SESSION_TITLE);
      await loadSessions();
      setActiveId(created.id);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, [loadSessions]);

  const removeSession = useCallback(
    async (id) => {
      try {
        await api.deleteSession(id);
        const remaining = await loadSessions();
        if (id === activeId) {
          setActiveId(remaining.length > 0 ? remaining[0].id : null);
        }
      } catch (err) {
        setError(err.message);
      }
    },
    [activeId, loadSessions],
  );

  const ask = useCallback(
    async (question) => {
      if (!activeId) return;

      const streamingId = `streaming-${Date.now()}`;
      setPending(true);
      setMessages((current) => [
        ...current,
        {
          id: `optimistic-${Date.now()}`,
          role: 'user',
          content: question,
          citations: [],
          created_at: new Date().toISOString(),
        },
        {
          // The assistant turn is inserted empty and filled as tokens arrive.
          // `streaming: true` tells the bubble to render the text plainly:
          // citation markers are not resolved until the answer is complete,
          // and rendering an unresolved [1] as a broken link mid-stream would
          // flicker every marker from broken to valid as the reply lands.
          id: streamingId,
          role: 'assistant',
          content: '',
          citations: [],
          streaming: true,
          created_at: new Date().toISOString(),
        },
      ]);

      const appendToken = (text) =>
        setMessages((current) =>
          current.map((message) =>
            message.id === streamingId
              ? { ...message, content: message.content + text }
              : message,
          ),
        );

      try {
        let failed = null;

        await api.streamQuery(activeId, question, ({ event, data }) => {
          if (event === 'token') {
            appendToken(data.text);
          } else if (event === 'done') {
            // Citations arrive validated, once. Swapping them in here is what
            // turns the plain text into a cited answer.
            setMessages((current) =>
              current.map((message) =>
                message.id === streamingId
                  ? {
                      ...message,
                      id: data.message_id,
                      citations: data.citations ?? [],
                      streaming: false,
                    }
                  : message,
              ),
            );
          } else if (event === 'error') {
            failed = data.detail;
          }
        });

        if (failed) {
          // Drop the partial answer rather than leaving half a reply on
          // screen presented as if it were finished.
          setMessages((current) =>
            current.filter((message) => message.id !== streamingId),
          );
          setError(failed);
        } else {
          setError(null);
        }

        await loadSessions();
      } catch (err) {
        setMessages((current) =>
          current.filter((message) => message.id !== streamingId),
        );
        setError(err.message);
      } finally {
        setPending(false);
      }
    },
    [activeId, loadSessions],
  );

  return {
    sessions,
    activeId,
    messages,
    pending,
    error,
    selectSession: setActiveId,
    startSession,
    removeSession,
    ask,
  };
}
