import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./auth";
import { loadApiBaseUrl } from "./config";
import "./styles.css";

function Bootstrap() {
  const [apiBaseUrl, setApiBaseUrl] = useState<string | null>(null);
  const reviewerPortal = window.location.pathname === "/reviewer" || window.location.pathname.startsWith("/reviewer/");
  useEffect(() => {
    let live = true;
    const refresh = () => { void loadApiBaseUrl().then((url) => { if (live) setApiBaseUrl(url); }); };
    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => { live = false; window.clearInterval(timer); };
  }, []);
  if (apiBaseUrl === null) return <div className="app-loading"><div className="loading-mark">वि</div><span>Connecting to VidhiLens…</span></div>;
  if (!apiBaseUrl) return <main className="connection-shell"><section className="connection-card">
    <div className="loading-mark">वि</div>
    <span className="connection-status"><i /> {reviewerPortal ? "Reviewer workspace" : "VidhiLens"} · reconnecting</span>
    <h1>{reviewerPortal ? "The review workspace is waiting for its backend." : "Guidance is temporarily unavailable."}</h1>
    <p>{reviewerPortal ? "Start the Colab notebook with Run All. This page will connect automatically when the model is ready." : "Please try again shortly. You can leave this page open; it will reconnect automatically when service resumes."}</p>
    <button className="button button--primary" onClick={() => void loadApiBaseUrl().then(setApiBaseUrl)}>Check connection</button>
  </section></main>;
  return <App initialApiBaseUrl={apiBaseUrl} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode><AuthProvider><Bootstrap /></AuthProvider></StrictMode>,
);
