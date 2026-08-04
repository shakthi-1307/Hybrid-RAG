import { useCallback, useEffect, useState } from 'react';

import { api } from '../api/client.js';
import { INGESTION_POLL_INTERVAL_MS, PENDING_STATUSES } from '../config.js';

export function useDocuments() {
  const [documents, setDocuments] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await api.listDocuments());
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const stillWorking = documents.some((doc) =>
      PENDING_STATUSES.includes(doc.status),
    );
    if (!stillWorking) return undefined;

    const timer = setInterval(refresh, INGESTION_POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [documents, refresh]);

  const upload = useCallback(
    async (file) => {
      setBusy(true);
      try {
        await api.uploadDocument(file);
        await refresh();
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const remove = useCallback(
    async (id) => {
      try {
        await api.deleteDocument(id);
        await refresh();
      } catch (err) {
        setError(err.message);
      }
    },
    [refresh],
  );

  return { documents, busy, error, upload, remove };
}
