import { useState } from 'react';

import { PASSWORD_MIN_LENGTH } from '../config.js';

export function LoginPage({ error, onSignIn, onSignUp }) {
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await (registering ? onSignUp : onSignIn)(email, password);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-screen">
      <form className="auth-card" onSubmit={submit}>
        <h1>Hybrid RAG</h1>
        <p className="subtitle">
          {registering
            ? 'Create an account to build your own knowledge base.'
            : 'Sign in to your documents and chat history.'}
        </p>

        <label>
          Email
          <input
            type="email"
            value={email}
            autoComplete="email"
            required
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            minLength={PASSWORD_MIN_LENGTH}
            autoComplete={registering ? 'new-password' : 'current-password'}
            required
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        {registering && (
          <p className="hint">At least {PASSWORD_MIN_LENGTH} characters.</p>
        )}
        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={submitting}>
          {submitting ? 'Working…' : registering ? 'Create account' : 'Sign in'}
        </button>

        <button
          type="button"
          className="link-button"
          onClick={() => setRegistering((current) => !current)}
        >
          {registering
            ? 'Already have an account? Sign in'
            : 'Need an account? Register'}
        </button>
      </form>
    </div>
  );
}
