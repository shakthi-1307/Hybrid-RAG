import { LoginPage } from './components/LoginPage.jsx';
import { Workspace } from './components/Workspace.jsx';
import { useAuth } from './hooks/useAuth.js';

export default function App() {
  const auth = useAuth();

  if (auth.checking) {
    return <div className="boot">Checking your session…</div>;
  }

  if (!auth.user) {
    return (
      <LoginPage
        error={auth.error}
        onSignIn={auth.signIn}
        onSignUp={auth.signUp}
      />
    );
  }

  // Keying on the user id discards every cached document and conversation when
  // the account changes, so one user's data cannot survive into another's view.
  return (
    <Workspace key={auth.user.id} user={auth.user} onSignOut={auth.signOut} />
  );
}
