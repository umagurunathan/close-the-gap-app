import { initializeApp } from "@firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut } from "@firebase/auth";

export const firebaseAuthEnabled = import.meta.env.VITE_FIREBASE_AUTH_ENABLED === "true";
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};
const requiredConfig = ["apiKey", "authDomain", "projectId", "appId"];
const missingConfig = requiredConfig.filter((key) => !firebaseConfig[key]);

export const firebaseConfigError = firebaseAuthEnabled && missingConfig.length
  ? `Firebase sign-in is enabled, but its web app configuration is missing: ${missingConfig.join(", ")}.`
  : "";

export const firebaseAuth = firebaseAuthEnabled && !firebaseConfigError
  ? getAuth(initializeApp(firebaseConfig))
  : null;

export async function signInWithGoogle() {
  if (!firebaseAuth) throw new Error(firebaseConfigError || "Firebase sign-in is not configured.");
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  await signInWithPopup(firebaseAuth, provider);
}

export async function signOutGoogle() {
  if (firebaseAuth) await signOut(firebaseAuth);
}
