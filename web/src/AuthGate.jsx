import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { onAuthStateChanged } from "@firebase/auth";
import { setAuthTokenProvider } from "./api.js";
import { firebaseAuth, firebaseAuthEnabled, firebaseConfigError, signInWithGoogle, signOutGoogle } from "./firebase.js";

// One app for everyone: without signing in you are a guest in the demo; "Sign in with Google" (in the
// Demo controls) turns you into yourself, and the backend then shows only your own work. This wrapper never blocks
// the app: it only tells it who is signed in, and adds the sign-in token to every request.
const AuthContext = createContext({ enabled: false, ready: true, user: null, signIn: async () => {}, signOut: async () => {} });

export function useAuth() {
  return useContext(AuthContext);
}

export default function AuthGate({ children }) {
  const enabled = firebaseAuthEnabled && !firebaseConfigError;
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(!enabled);   // until Firebase answers, we don't know if someone is signed in

  useEffect(() => {
    if (!enabled) return undefined;
    return onAuthStateChanged(firebaseAuth, (next) => {
      setAuthTokenProvider(next ? () => next.getIdToken() : null);
      setUser(next);
      setReady(true);
    }, () => {
      setAuthTokenProvider(null);
      setUser(null);
      setReady(true);
    });
  }, [enabled]);

  const signIn = useCallback(async () => { await signInWithGoogle(); }, []);
  const signOut = useCallback(async () => { await signOutGoogle(); }, []);

  return (
    <AuthContext.Provider value={{ enabled, ready, user, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}
