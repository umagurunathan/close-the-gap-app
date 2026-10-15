import { createContext, useContext, useEffect, useState } from "react";
import { onAuthStateChanged } from "@firebase/auth";
import { setAuthTokenProvider } from "./api.js";
import {
  firebaseAuth,
  firebaseAuthEnabled,
  firebaseConfigError,
  signInWithGoogle,
  signOutGoogle,
} from "./firebase.js";

const AuthContext = createContext({ enabled: false, user: null, signOut: async () => {} });

export function useAuth() {
  return useContext(AuthContext);
}

export default function AuthGate({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(!firebaseAuthEnabled);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!firebaseAuth) return undefined;
    return onAuthStateChanged(firebaseAuth, (nextUser) => {
      setUser(nextUser);
      setAuthTokenProvider(nextUser ? () => nextUser.getIdToken() : null);
      setReady(true);
    }, () => {
      setUser(null);
      setAuthTokenProvider(null);
      setError("Could not verify your sign-in. Please reload and try again.");
      setReady(true);
    });
  }, []);

  async function signIn() {
    setError("");
    try {
      await signInWithGoogle();
    } catch (err) {
      setError(err.message || "Google sign-in did not complete.");
    }
  }

  async function signOut() {
    setError("");
    try {
      await signOutGoogle();
    } catch (err) {
      setError(err.message || "Could not sign out.");
    }
  }

  if (firebaseAuthEnabled && firebaseConfigError) {
    return <div className="auth-page"><section className="auth-card"><h1>Sign-in setup needed</h1><p>{firebaseConfigError}</p></section></div>;
  }
  if (firebaseAuthEnabled && !ready) {
    return <div className="auth-page"><section className="auth-card"><p>Checking your sign-in…</p></section></div>;
  }
  if (firebaseAuthEnabled && !user) {
    return (
      <div className="auth-page">
        <section className="auth-card">
          <div className="brand">Close the Gap</div>
          <p>Sign in with the Google account linked to your company directory to view your meetings and absence actions.</p>
          {error && <div className="note warn" role="alert">{error}</div>}
          <button className="primary" type="button" onClick={signIn}>Continue with Google</button>
          <p className="auth-help">After signing in, connect Google Calendar to import your meetings into the company workspace.</p>
          <a className="public-demo-link" href="/demo">Continue as guest with fictional demo data</a>
        </section>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ enabled: firebaseAuthEnabled, user, signOut }}>
      {children}
      {error && <div className="auth-error" role="alert">{error}</div>}
    </AuthContext.Provider>
  );
}
