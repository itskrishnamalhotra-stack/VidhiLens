import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LegalAiApi } from "./api";
import { useAuth } from "./auth";
import { firebaseConfigured } from "./config";
import type { ComplaintDraft, Message, MyIdentity, ReviewCase, Session } from "./types";
import { DraftPanel } from "./components/DraftPanel";
import { Icon } from "./components/Icon";
import { LoginScreen } from "./components/LoginScreen";
import { ProvisionCard } from "./components/ProvisionCard";
import { Sidebar } from "./components/Sidebar";
import { CasesPanel } from "./components/CasesPanel";
import { collapseOptimisticDuplicates, mergeMessages } from "./messageMerge";

interface Props {
  initialApiBaseUrl: string;
}

function messageTime(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function displayUserMessage(value: string) {
  const answer = value.match(/^.+\?\nAnswer:\s*(.+)$/s);
  return answer ? answer[1].trim() : value;
}

function friendlyError(reason: unknown) {
  if (!(reason instanceof Error)) return "Something went wrong. Please try again.";
  if (reason.message.includes("fetch")) return "The backend cannot be reached. Check that Colab and the tunnel are still running.";
  return reason.message;
}

function outcomeLabel(outcome: string) {
  if (outcome === "provision_match") return "Possible provisions found";
  if (outcome === "insufficient_information") return "More information needed";
  return "No supported provision identified";
}

function Welcome({ displayName, onExample, isReviewer = false }: { displayName: string; onExample: (text: string) => void; isReviewer?: boolean }) {
  const firstName = displayName.trim().split(/\s+/)[0] || "there";
  const examples = isReviewer ? [
    { label: "Property report", text: "A reporter says their phone was taken from a bag without consent. Which reviewed provisions may apply and what facts should I verify?" },
    { label: "Online fraud", text: "A reporter says someone used an OTP to transfer money. Which BNS or IT Act provisions may apply?" },
    { label: "Impersonation", text: "A reporter describes a fake online profile using their identity. What should I verify before reviewing it?" },
  ] : [
    { label: "Theft", text: "My phone was taken from my bag without my permission." },
    { label: "Online fraud", text: "Someone used my OTP and bank details to transfer money." },
    { label: "Impersonation", text: "A person created a fake profile pretending to be me online." },
  ];
  return (
    <div className="welcome">
      <div className="welcome-emblem"><Icon name="shield" /></div>
      <p className="eyebrow">{isReviewer ? "Source-grounded research" : "A private place to begin"}</p>
      <h1>{isReviewer ? `Hi ${firstName}. Research a report.` : `Hi ${firstName}. Tell me what happened.`}</h1>
      <p>{isReviewer ? "Describe reported facts or ask which reviewed BNS and IT Act provisions may apply. Open Reports to act on a submitted case." : "Write naturally in English, Hindi, or Hinglish. You can ask a question or describe an incident. We will go one step at a time."}</p>
      <div className="example-grid">
        {examples.map((example) => <button key={example.label} onClick={() => onExample(example.text)}>
          <span className="example-label">{example.label}</span><span>{example.text}</span>
        </button>)}
      </div>
    </div>
  );
}

function AssistantMessage({ message, onReply, onPrepareReply, onDraft, onOpenDraft, busy, isReviewer }: {
  message: Message;
  onReply: (text: string) => void;
  onPrepareReply: (text: string) => void;
  onDraft: () => void;
  onOpenDraft: (draftId: string) => void;
  busy: boolean;
  isReviewer: boolean;
}) {
  const structured = message.structured;
  const analysis = structured?.analysis;
  const repeatedQuestion = !structured?.next_question &&
    analysis?.uncertain_sections?.[0]?.missing_facts?.trim() === message.text.trim();
  return (
    <div className="message-row message-row--assistant">
      <div className="assistant-avatar">वि</div>
      <div className="message-content">
        <div className="message-author"><strong>VidhiLens</strong><span>{messageTime(message.created_at)}</span></div>
        <div className={`assistant-card ${analysis ? "" : "assistant-card--conversation"}`}>
          {!repeatedQuestion && <p className="assistant-text">{message.text}</p>}
          {structured?.suggestions && structured.suggestions.length > 0 && (
            <div className="conversation-suggestions">
              {structured.suggestions.map((suggestion) => (
                <button key={suggestion.label} disabled={busy} onClick={() => onPrepareReply(suggestion.prefill)}>
                  {suggestion.label}<Icon name="chevron" />
                </button>
              ))}
            </div>
          )}
          {!isReviewer && structured?.action === "review_draft" && structured.draft_id && (
            <div className="draft-offer">
              <span><Icon name="file" /><span><strong>Your report draft is ready</strong><small>Open it to review, edit, save, or continue to send.</small></span></span>
              <button className="button button--primary" disabled={busy} onClick={() => onOpenDraft(structured.draft_id!)}>Open report</button>
            </div>
          )}
          {!analysis && structured?.next_question?.text && <div className="guided-options">
            {(structured.next_question.options || []).map((option) => <button key={option} disabled={busy}
              onClick={() => onReply(`${structured.next_question?.text}\nAnswer: ${option}`)}>{option}</button>)}
          </div>}
          {analysis && (
            <>
              <div className={`outcome outcome--${analysis.outcome}`}>
                <Icon name={analysis.outcome === "provision_match" ? "check" : analysis.outcome === "insufficient_information" ? "spark" : "shield"} />
                <span><strong>{outcomeLabel(analysis.outcome)}</strong><small>{analysis.outcome === "out_of_scope"
                  ? "The current product covers reviewed BNS and IT Act provisions."
                  : "Possible provisions for research guidance; this is not a finding of guilt or legal advice."}</small></span>
              </div>
              {analysis.provisions?.length > 0 && <details className="legal-details" open={isReviewer}>
                <summary>See possible sections and official text</summary>
                <div className="provision-stack">
                  {analysis.provisions.map((item) => <ProvisionCard key={item.provision_id} provision={item} />)}
                </div>
              </details>}
              {!structured.next_question && analysis.uncertain_sections?.slice(0, 1).map((uncertain) => (
                <div className="fact-question" key={`${uncertain.provision_id}-${uncertain.missing_facts}`}>
                  <div className="fact-question__head"><Icon name="spark" /><span><small>One detail can improve the result</small><strong>{uncertain.missing_facts}</strong></span></div>
                  <div className="option-row">
                    {Array.from(new Set([...(uncertain.options?.length ? uncertain.options : ["Yes", "No", "Not sure"]), "Other"])).map((option) => (
                      <button key={option} disabled={busy} onClick={() => option.toLowerCase() === "other"
                        ? onPrepareReply(`${uncertain.missing_facts}\nAnswer: `)
                        : onReply(`${uncertain.missing_facts}\nAnswer: ${option}`)}>{option}</button>
                    ))}
                  </div>
                </div>
              ))}
              {structured.next_question?.text && <div className="guided-options">
                {(structured.next_question.options || []).map((option) => <button key={option} disabled={busy}
                  onClick={() => onReply(`${structured.next_question?.text}\nAnswer: ${option}`)}>{option}</button>)}
                <button disabled={busy} onClick={() => onPrepareReply(`${structured.next_question?.text}\nAnswer: `)}>Write my answer</button>
              </div>}
              {!isReviewer && analysis.can_prepare_draft && (
                <div className="draft-offer">
                  <span><Icon name="file" /><span><strong>Prepare a complaint draft</strong><small>Review and edit every detail before saving it locally.</small></span></span>
                  <button className="button button--primary" disabled={busy} onClick={onDraft}>Prepare draft</button>
                </div>
              )}
              <div className="analysis-meta"><Icon name="book" /> Checked against reviewed BNS and IT Act sources</div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SettingsDialog({ apiBaseUrl, onSave, onClose }: {
  apiBaseUrl: string;
  onSave: (value: string) => void;
  onClose: () => void;
}) {
  const [value, setValue] = useState(apiBaseUrl);
  return (
    <div className="modal-backdrop">
      <section className="settings-dialog" role="dialog" aria-modal="true" aria-label="Settings">
        <header><div><p className="eyebrow">Connection</p><h2>Backend settings</h2></div><button className="icon-button" onClick={onClose}><Icon name="close" /></button></header>
        <label>API endpoint<input value={value} onChange={(event) => setValue(event.target.value)} placeholder="https://…trycloudflare.com" /></label>
        <p>The temporary Cloudflare address works only while its Colab runtime remains open. Firebase Hosting can use the same interface with a permanent backend later.</p>
        <footer><button className="button button--ghost" onClick={onClose}>Cancel</button><button className="button button--primary" onClick={() => onSave(value)}>Save connection</button></footer>
      </section>
    </div>
  );
}

export default function App({ initialApiBaseUrl }: Props) {
  const auth = useAuth();
  const reviewerPortal = window.location.pathname === "/reviewer" || window.location.pathname.startsWith("/reviewer/");
  const [apiBaseUrl, setApiBaseUrl] = useState(initialApiBaseUrl);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [composer, setComposer] = useState("");
  const [loadingSession, setLoadingSession] = useState(false);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draft, setDraft] = useState<ComplaintDraft | null>(null);
  const [cases, setCases] = useState<ReviewCase[]>([]);
  const [drafts, setDrafts] = useState<ComplaintDraft[]>([]);
  const [identity, setIdentity] = useState<MyIdentity | null>(null);
  const [casesOpen, setCasesOpen] = useState(false);
  const [urgentHelp, setUrgentHelp] = useState<"fraud" | "emergency" | null>(null);
  const [sending, setSending] = useState(false);
  const [draftBusy, setDraftBusy] = useState(false);
  const [processingLabel, setProcessingLabel] = useState("Understanding your message…");
  const busy = sending || draftBusy;
  const endRef = useRef<HTMLDivElement>(null);
  const conversationRef = useRef<HTMLElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  // React state updates are asynchronous. This synchronous lock prevents a
  // rapid Enter/click pair from submitting the same text twice.
  const sendLockRef = useRef(false);
  const api = useMemo(() => new LegalAiApi(apiBaseUrl, auth.authHeaders), [apiBaseUrl, auth.authHeaders]);
  const visibleMessages = useMemo(() => collapseOptimisticDuplicates(messages), [messages]);

  const saveApiUrl = (value: string) => {
    if (firebaseConfigured) return;
    const clean = value.trim().replace(/\/$/, "");
    if (!clean) return;
    localStorage.setItem("legalai.apiBaseUrl", clean);
    setApiBaseUrl(clean);
    setSettingsOpen(false);
    setError("");
  };

  const refreshSessions = useCallback(async (preferred?: string) => {
    const list = await api.listSessions();
    setSessions(list);
    setActiveSessionId((current) => preferred ?? current);
  }, [api]);

  const refreshRecords = useCallback(async () => {
    const [caseRows, draftRows, profile] = await Promise.all([
      api.listCases(), api.listDrafts(), api.me(),
    ]);
    setCases(caseRows); setDrafts(draftRows); setIdentity(profile);
  }, [api]);

  useEffect(() => {
    if (!auth.user) return;
    setIdentity(null);
    setError("");
    refreshSessions().catch((reason) => setError(friendlyError(reason)));
    refreshRecords().catch((reason) => setError(friendlyError(reason)));
  }, [auth.user, refreshSessions, refreshRecords]);

  useEffect(() => {
    if (!auth.user || !identity) return;
    if (identity.is_admin && !reviewerPortal) window.location.replace("/reviewer");
  }, [auth.user, identity, reviewerPortal]);

  useEffect(() => {
    if (!auth.user) return;
    const timer = window.setInterval(() => { void refreshRecords().catch(() => {}); }, 30_000);
    return () => window.clearInterval(timer);
  }, [auth.user, refreshRecords]);

  useEffect(() => {
    if (!auth.user || !activeSessionId) { setMessages([]); return; }
    let live = true;
    setLoadingSession(true);
    api.getSession(activeSessionId).then((session) => {
      if (live) setMessages(session.messages || []);
    }).catch((reason) => live && setError(friendlyError(reason))).finally(() => live && setLoadingSession(false));
    return () => { live = false; };
  }, [activeSessionId, api, auth.user]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const conversation = conversationRef.current;
      if (conversation) conversation.scrollTop = conversation.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages, busy, activeSessionId]);

  useEffect(() => {
    const area = composerRef.current;
    if (!area) return;
    area.style.height = "auto";
    area.style.height = `${Math.min(area.scrollHeight, 150)}px`;
  }, [composer]);

  useEffect(() => {
    if (!sending) return;
    setProcessingLabel("Understanding your message…");
    const retrieval = window.setTimeout(() => setProcessingLabel("Checking whether legal guidance is needed…"), 3200);
    const grounding = window.setTimeout(() => setProcessingLabel("Checking legal sources and preparing the answer…"), 7600);
    return () => { window.clearTimeout(retrieval); window.clearTimeout(grounding); };
  }, [sending]);

  if (auth.loading) return <div className="app-loading"><div className="loading-mark">वि</div><span>Opening your workspace…</span></div>;
  if (!auth.user) return <LoginScreen apiBaseUrl={apiBaseUrl} onApiBaseUrl={saveApiUrl} reviewerPortal={reviewerPortal} />;
  if (!identity) return <div className="app-loading"><div className="loading-mark">वि</div><span>Checking account access…</span>{error && <p>{error}</p>}</div>;
  if (reviewerPortal && !identity.is_admin) return <div className="app-loading"><div className="loading-mark">वि</div><strong>Reviewer access is not enabled for this account.</strong><button onClick={() => void auth.logout()}>Sign out</button></div>;
  if (!reviewerPortal && identity.is_admin) return <div className="app-loading"><div className="loading-mark">वि</div><span>Opening reviewer workspace…</span></div>;

  const startNew = () => {
    setCasesOpen(false);
    setActiveSessionId(null);
    setMessages([]);
    setComposer("");
    setSidebarOpen(false);
    setError("");
    setUrgentHelp(null);
  };

  const openDraftById = async (draftId: string) => {
    setDraftBusy(true);
    setError("");
    try {
      setDraft(await api.getDraft(draftId));
      void refreshRecords().catch(() => {});
    } catch (reason) {
      setError(friendlyError(reason));
    } finally {
      setDraftBusy(false);
    }
  };

  const send = async (text = composer) => {
    const clean = text.trim();
    if (!clean || sendLockRef.current) return;
    sendLockRef.current = true;
    setSending(true);
    setError("");
    setComposer("");
    if (/\b(?:upi|bank|card|wallet|payment|transaction|money)\b/i.test(clean) &&
        /\b(?:fraud|scam|stole|taken|sent|transferred|lost|debit|otp)\b/i.test(clean)) setUrgentHelp("fraud");
    else if (/\b(?:immediate danger|attack(?:ing)? me|kill me|unsafe right now)\b/i.test(clean)) setUrgentHelp("emergency");
    let temporaryId: string | null = null;
    try {
      let sessionId = activeSessionId;
      if (!sessionId) {
        const created = await api.createSession(identity?.is_admin ? "New research" : "New chat");
        sessionId = created.session_id;
        setActiveSessionId(sessionId);
        setSessions((current) => [created, ...current]);
      }
      const temporary: Message = { id: `local-${Date.now()}-${crypto.randomUUID()}`, role: "user", text: clean, created_at: new Date().toISOString() };
      temporaryId = temporary.id;
      setMessages((current) => [...current, temporary]);
      const turn = await api.sendMessage(sessionId, clean);
      setMessages((current) => mergeMessages(
        current,
        [turn.user_message, turn.assistant_message],
        [temporary.id],
      ));
      if (!identity?.is_admin && turn.assistant_message.structured?.action === "review_draft" &&
          turn.assistant_message.structured.draft_id) {
        await openDraftById(turn.assistant_message.structured.draft_id);
      }
      await refreshSessions(sessionId).catch((reason) => setError(friendlyError(reason)));
    } catch (reason) {
      setComposer(clean);
      if (temporaryId) {
        setMessages((current) => current.filter((item) => item.id !== temporaryId));
      }
      setError(friendlyError(reason));
    } finally {
      sendLockRef.current = false;
      setSending(false);
      window.setTimeout(() => composerRef.current?.focus(), 0);
    }
  };

  const submit = (event: FormEvent) => { event.preventDefault(); void send(); };
  const openDraft = async () => {
    if (!activeSessionId || identity?.is_admin) return;
    setDraftBusy(true); setError("");
    try {
      const existing = drafts.find((item) => item.session_id === activeSessionId && item.status !== "cancelled");
      setDraft(existing ? await api.getDraft(existing.draft_id) : await api.createDraft(activeSessionId));
      await refreshRecords();
    }
    catch (reason) { setError(friendlyError(reason)); }
    finally { setDraftBusy(false); }
  };
  const draftAction = async (action: () => Promise<ComplaintDraft | void>) => {
    if (!draft) return;
    setDraftBusy(true); setError("");
    try {
      const result = await action();
      if (result) setDraft(result);
      else setDraft(null);
      await refreshRecords();
    } catch (reason) { setError(friendlyError(reason)); }
    finally { setDraftBusy(false); }
  };

  const advanceDraft = async (changes: Record<string, string>, destination: "send" | "later"): Promise<boolean> => {
    if (!draft) return false;
    setDraftBusy(true); setError("");
    try {
      let current = draft;
      if (Object.keys(changes).length > 0) current = await api.patchDraft(current.draft_id, current.version, changes);
      if (destination === "send") {
        if (current.status === "needs_reanalysis") current = await api.reanalyzeDraft(current.draft_id, current.version);
        if (current.status === "preview") current = await api.confirmDraft(current.draft_id, current.version);
      }
      setDraft(current);
      await refreshRecords();
      return destination === "later" || current.status === "saved";
    } catch (reason) {
      setError(friendlyError(reason));
      return false;
    } finally { setDraftBusy(false); }
  };

  const removeChat = async (sessionId: string) => {
    const submitted = cases.some((item) => item.session_id === sessionId);
    const message = submitted
      ? "Archive this conversation? Its submitted case will remain in My cases."
      : "Delete this unfinished conversation and its drafts permanently?";
    if (!window.confirm(message)) return;
    try {
      await api.removeSession(sessionId);
      if (activeSessionId === sessionId) startNew();
      await refreshSessions(); await refreshRecords();
      if (activeSessionId === sessionId) setActiveSessionId(null);
    } catch (reason) { setError(friendlyError(reason)); }
  };

  const submitCase = async (role: "self" | "witness" | "on_behalf", relationship: string, affectedPersonName: string) => {
    if (!draft) return;
    setDraftBusy(true); setError("");
    try {
      await api.submitCase(draft.draft_id, role, relationship, affectedPersonName);
      await refreshRecords();
      setDraft(null); setCasesOpen(true);
    } catch (reason) { setError(friendlyError(reason)); }
    finally { setDraftBusy(false); }
  };

  return (
    <div className="app-shell">
      <Sidebar user={auth.user} sessions={sessions} activeSessionId={activeSessionId} open={sidebarOpen}
        isReviewer={Boolean(identity?.is_admin)}
        onSelect={(id) => { setActiveSessionId(id); setSidebarOpen(false); }} onNew={startNew}
        onSettings={() => setSettingsOpen(true)} onLogout={() => void auth.logout()} onClose={() => setSidebarOpen(false)}
        onRemove={(id) => void removeChat(id)} onCases={() => { setCasesOpen(true); setSidebarOpen(false); }} />
      {sidebarOpen && <button className="sidebar-scrim" aria-label="Close menu" onClick={() => setSidebarOpen(false)} />}

      <main className="workspace">
        <header className="workspace-head">
          <button className="icon-button mobile-menu" aria-label="Open conversations" onClick={() => setSidebarOpen(true)}><Icon name="menu" /></button>
          <div><strong>{sessions.find((item) => item.session_id === activeSessionId)?.title || (identity?.is_admin ? "Research chat" : "New chat")}</strong><span>{identity?.is_admin ? "Reviewer · research workspace" : "VidhiLens · private guidance"}</span></div>
          <button className="header-cases" onClick={() => setCasesOpen(true)}>{identity?.is_admin ? "Reports" : "My cases"}{!identity?.is_admin && cases.some((item) => item.status === "information_requested") && <b>!</b>}</button>
        </header>

        <section className="conversation" ref={conversationRef} aria-live="polite">
          {urgentHelp && <div className="urgent-strip" role="alert">
            <span>{urgentHelp === "fraud" ? "Recent money or account fraud? Act quickly." : "Are you in immediate danger?"}</span>
            <a href={`tel:${urgentHelp === "fraud" ? "1930" : "112"}`}>Call {urgentHelp === "fraud" ? "1930" : "112"}</a>
            {urgentHelp === "fraud" && <a href="https://www.cybercrime.gov.in/" target="_blank" rel="noreferrer">Official cybercrime portal</a>}
            <button aria-label="Dismiss urgent help" onClick={() => setUrgentHelp(null)}>×</button>
          </div>}
          <div className="conversation-inner">
            {!activeSessionId && messages.length === 0 && <Welcome displayName={auth.user.displayName} isReviewer={Boolean(identity?.is_admin)} onExample={(text) => {
              setComposer(text); window.setTimeout(() => composerRef.current?.focus(), 0);
            }} />}
            {loadingSession && <div className="session-loading"><span /><span /><span /></div>}
            {visibleMessages.map((message) => message.role === "user" ? (
              <div className="message-row message-row--user" key={message.id}>
                <div className="message-content"><div className="message-author"><strong>You</strong><span>{messageTime(message.created_at)}</span></div><div className="user-bubble">{displayUserMessage(message.text)}</div></div>
              </div>
            ) : <AssistantMessage key={message.id} message={message} onReply={(text) => void send(text)}
              onPrepareReply={(text) => { setComposer(text); window.setTimeout(() => composerRef.current?.focus(), 0); }}
              onDraft={() => void openDraft()} onOpenDraft={(id) => void openDraftById(id)}
              busy={busy} isReviewer={Boolean(identity?.is_admin)} />)}
            {sending && <div className="message-row message-row--assistant"><div className="assistant-avatar">वि</div><div className="thinking">
              <div className="thinking-dots"><span /><span /><span /></div><div><strong>{processingLabel}</strong><small>The full source check can take a few seconds.</small></div>
            </div></div>}
            <div ref={endRef} />
          </div>
        </section>

        <footer className="composer-wrap">
          {error && <div className="error-bar"><span>{error}</span><button onClick={() => setError("")}><Icon name="close" /></button></div>}
          <form className="composer" onSubmit={submit}>
            <textarea ref={composerRef} rows={1} value={composer} disabled={sending} placeholder={identity?.is_admin ? "Describe the report or ask about a provision…" : "Write a message…"}
              onChange={(event) => setComposer(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} />
            <button disabled={sending || composer.trim().length < 3} aria-label="Send message"><Icon name="send" /></button>
          </form>
          <div className="composer-meta"><span>Enter to send · Shift + Enter for a new line</span><span>Verify important information with the official source.</span></div>
        </footer>
      </main>

      {settingsOpen && (firebaseConfigured ? <div className="modal-backdrop"><section className="settings-dialog" role="dialog" aria-modal="true" aria-label="Connection"><header><div><p className="eyebrow">Connection</p><h2>Connected automatically</h2></div><button className="icon-button" onClick={() => setSettingsOpen(false)}><Icon name="close" /></button></header><p>VidhiLens discovers the active Colab backend automatically. Keep the Colab runtime running while using the app.</p></section></div> : <SettingsDialog apiBaseUrl={apiBaseUrl} onSave={saveApiUrl} onClose={() => setSettingsOpen(false)} />)}
      {draft && <DraftPanel draft={draft} busy={busy} error={error} onClose={() => setDraft(null)}
        onAdvance={advanceDraft}
        onCancel={() => draftAction(() => api.cancelDraft(draft.draft_id, draft.version))}
        onDelete={() => draftAction(() => api.deleteDraft(draft.draft_id))}
        onSubmitCase={submitCase} alreadySubmitted={cases.some((item) => item.draft_id === draft.draft_id)} />}
      {casesOpen && <CasesPanel api={api} cases={cases} drafts={drafts} isAdmin={Boolean(identity?.is_admin)}
        onClose={() => setCasesOpen(false)} onRefresh={refreshRecords}
        onResearch={(report) => { setCasesOpen(false); setActiveSessionId(null); setMessages([]); setComposer(report.submission.fields.incident_description); window.setTimeout(() => composerRef.current?.focus(), 0); }}
        onOpenDraft={(id) => { void api.getDraft(id).then(setDraft).catch((reason) => setError(friendlyError(reason))); setCasesOpen(false); }}
        onOpenSession={(id) => { setActiveSessionId(id); setCasesOpen(false); }} />}
    </div>
  );
}
