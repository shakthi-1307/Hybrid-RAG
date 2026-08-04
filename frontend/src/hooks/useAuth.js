import { useCallback, useEffect, useState } from 'react';

import { api } from '../api/client.js';

export function useAuth() {
  const [user, setUser] = useState(null);
  // True until the cookie has been checked, so we never flash the login form
  // at someone who is already signed in.
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);

  const authenticate = useCallback(async (call) => {
    try {
      setUser(await call());
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const signIn = useCallback(
    (email, password) => authenticate(() => api.login(email, password)),
    [authenticate],
  );

  const signUp = useCallback(
    (email, password) => authenticate(() => api.register(email, password)),
    [authenticate],
  );

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
      setError(null);
    }
  }, []);

  return { user, checking, error, signIn, signUp, signOut };
}
