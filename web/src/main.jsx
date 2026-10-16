import React from "react";
import { createRoot } from "react-dom/client";
import AuthGate from "./AuthGate.jsx";
import App from "./App.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <AuthGate><App /></AuthGate>
    </ErrorBoundary>
  </React.StrictMode>
);
