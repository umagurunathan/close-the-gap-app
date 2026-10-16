import { Component } from "react";

// The safety net: if anything on the page fails to display, show a polite message with a Reload button instead of a
// blank white page. (Errors from the server are shown in the message bar; this catches the unexpected ones.)
export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    console.error("Close the Gap could not display the page:", error, info?.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="crash" role="alert">
        <h1>Something went wrong</h1>
        <p>The page could not be displayed. Reloading usually fixes it; nothing you saved is lost.</p>
        <button className="primary" onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  }
}
