import { useCallback, useEffect, useState } from 'react';

import { api } from '../api/client.js';
import { INGESTION_POLL_INTERVAL_MS, PENDING_STATUSES } from '../config.js';

export function useDocuments() {
  const [documents, setDocuments] = useState([]);
  // Names of files currently being sent, so a drop of several shows a queue
  // rather than one opaque "uploading" state.
  const [uploading, setUploading] = useState([]);
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
    async (files) => {
      const queue = Array.from(files);
      if (queue.length === 0) return;

      setUploading(queue.map((file) => file.name));
      try {
        // Sequential on purpose: each upload triggers a background ingest that
        // loads models and embeds. Firing them in parallel would contend for
        // the same CPU and the same connection pool.
        for (const file of queue) {
          try {
            await api.uploadDocument(file);
            setError(null);
          } catch (err) {
            setError(`${file.name}: ${err.message}`);
          }
          setUploading((current) => current.filter((name) => name !== file.name));
        }
        await refresh();
      } finally {
        setUploading([]);
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

  return { documents, uploading, busy: uploading.length > 0, error, upload, remove };
}
