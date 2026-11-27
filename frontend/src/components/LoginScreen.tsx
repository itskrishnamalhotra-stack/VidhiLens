import { useState } from "react";
import { useAuth } from "../auth";
import { Icon } from "./Icon";

interface Props {
  apiBaseUrl: string;
  onApiBaseUrl: (value: string) => void;
  reviewerPortal: boolean;
}

export function LoginScreen({ apiBaseUrl, onApiBaseUrl, reviewerPortal }: Props) {
  const auth = useAuth();
  const [token, setToken] = useState("");
  const [error, setError] = useState("");

  const run = async (action: () => void | Promise<void>) => {
    try { setError(""); await action(); } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign in failed");
    }
  };

  return (
    <main className="login-shell">
      <div className="login-atmosphere" />
      <section className="login-story">
        <div className="brand brand--large">
          <div className="brand-mark"><span>वि</span></div>
          <div><strong>VidhiLens</strong><small>Legal complaint guidance</small></div>
        </div>
        <div className="login-copy">
          <p className="eyebrow">{reviewerPortal ? "Private reviewer workspace" : "BNS + Information Technology Act"}</p>
          <h1>{reviewerPortal ? "Review reports with source-grounded guidance." : "Understand the law that may relate to your complaint."}</h1>
          <p>{reviewerPortal ? "Sign in with your authorized reviewer account to examine submitted reports, request details, and follow up." : "Describe an incident in everyday language. VidhiLens asks focused questions, checks reviewed provisions, and helps prepare a clear complaint draft."}</p>
          <div className="trust-row">
            <span><Icon name="shield" /> Source-grounded</span>
            <span><Icon name="book" /> Verified law text</span>
            <span><Icon name="file" /> Draft before saving</span>
          </div>
        </div>
        <p className="legal-boundary">Research guidance only. It does not determine guilt, provide legal advice, or file a complaint with an authority.</p>
      </section>

      <section className="login-panel-wrap">
        <div className="login-panel">
          <div className="login-panel__head">
            <span className="status-dot" />
            <span>{auth.firebaseEnabled ? "Secure account access" : "Temporary development access"}</span>
          </div>
          <h2>{reviewerPortal ? "Reviewer sign in" : auth.firebaseEnabled ? "Continue to your workspace" : "Connect to the running demo"}</h2>
          <p>{auth.firebaseEnabled
            ? "Your conversations and drafts remain separate from every other user."
            : "Use the temporary endpoint and token created in the active Colab runtime."}</p>

          {auth.firebaseEnabled ? (
            <div className="login-actions">
              <button className="button button--primary button--wide" onClick={() => run(auth.signInGoogle)}>
                Continue with Google
              </button>
            </div>
          ) : (
            <div className="form-stack">
              <label>Backend URL<input value={apiBaseUrl} onChange={(e) => onApiBaseUrl(e.target.value)} placeholder="https://…trycloudflare.com" /></label>
              <label>{reviewerPortal ? "Private reviewer token" : "Temporary access token"}<input type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" /></label>
              <button className="button button--primary button--wide" onClick={() => run(() => auth.signInDemo(token, reviewerPortal ? "reviewer" : "krishna"))}>
                Open secure workspace
              </button>
            </div>
          )}
          {error && <div className="inline-error">{error}</div>}
          <div className="privacy-note"><Icon name="shield" /> Authentication tokens stay in this browser session and are never placed in chat messages.</div>
        </div>
      </section>
    </main>
  );
}
