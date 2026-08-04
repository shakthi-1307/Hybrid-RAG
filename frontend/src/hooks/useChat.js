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
      ]);

      try {
        await api.sendQuery(activeId, question);
        setMessages(await api.listMessages(activeId));
        await loadSessions();
        setError(null);
      } catch (err) {
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
