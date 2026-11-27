import { useEffect, useRef, useState } from "react";
import { LegalAiApi } from "../api";
import type { ComplaintDraft, ReviewCase } from "../types";

const statusNames: Record<ReviewCase["status"], string> = {
  submitted: "Received by VidhiLens",
  information_requested: "Your reply needed",
  under_review: "Being reviewed",
  ready_to_refer: "Ready for official reporting",
  out_of_scope: "Outside this service",
  closed: "Review finished",
};
const reviewerStatusNames: Record<ReviewCase["status"], string> = {
  ...statusNames,
  information_requested: "Awaiting reporter's reply",
};

const decisionNames = [
  ["request_information", "Ask for details"],
  ["under_review", "Mark under review"],
  ["ready_to_refer", "Ready to refer"],
  ["out_of_scope", "Outside scope"],
  ["close", "Close with reason"],
  ["reopen", "Reopen"],
] as const;

interface Props {
  api: LegalAiApi;
  cases: ReviewCase[];
  drafts: ComplaintDraft[];
  isAdmin: boolean;
  onClose: () => void;
  onRefresh: () => Promise<void>;
  onOpenDraft: (draftId: string) => void;
  onOpenSession: (sessionId: string) => void;
  onResearch?: (report: ReviewCase) => void;
}

export function CasesPanel({ api, cases, drafts, isAdmin, onClose, onRefresh, onOpenDraft, onOpenSession, onResearch }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReviewCase | null>(null);
  const [reviewQueue, setReviewQueue] = useState<ReviewCase[]>([]);
  const [reviewMode] = useState(isAdmin);
  const [expanded, setExpanded] = useState(false);
  const [caseSearch, setCaseSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [reply, setReply] = useState("");
  const [decision, setDecision] = useState<(typeof decisionNames)[number][0]>("request_information");
  const [reason, setReason] = useState("");
  const [reviewReason, setReviewReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const shownCases = (reviewMode ? reviewQueue : cases).filter((item) =>
    (statusFilter === "all" || item.status === statusFilter) &&
    (!caseSearch.trim() || [item.case_id, item.submission.fields.incident_description,
      item.submission.fields.reporter_name].some((value) =>
      (value || "").toLocaleLowerCase().includes(caseSearch.trim().toLocaleLowerCase())))
  );
  const availableDrafts = drafts.filter((draft) => !cases.some((item) => item.draft_id === draft.draft_id));

  const refreshDetail = async (id: string) => {
    setDetail(await api.getCase(id));
    await onRefresh();
    if (reviewMode) setReviewQueue(await api.listReviewCases());
  };

  useEffect(() => {
    if (!isAdmin) return;
    void api.listReviewCases().then(setReviewQueue)
      .catch((cause) => setError(cause instanceof Error ? cause.message : "Reports unavailable"));
  }, [api, isAdmin]);

  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    let active = true;
    api.getCase(selectedId).then((value) => { if (active) setDetail(value); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Case could not be opened"); });
    return () => { active = false; };
  }, [api, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    const timer = window.setInterval(() => {
      void api.getCase(selectedId).then(setDetail).catch(() => {});
      if (reviewMode) void api.listReviewCases().then(setReviewQueue).catch(() => {});
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [api, selectedId, reviewMode]);

  const act = async (action: () => Promise<unknown>): Promise<boolean> => {
    if (!selectedId) return false;
    setBusy(true); setError("");
    try { await action(); await refreshDetail(selectedId); return true; }
    catch (cause) { setError(cause instanceof Error ? cause.message : "The action failed"); return false; }
    finally { setBusy(false); }
  };

  const upload = (file: File | undefined) => {
    if (!file || !selectedId) return;
    if (file.size > 8_000_000 || !["image/jpeg", "image/png", "application/pdf"].includes(file.type)) {
      setError("Choose a JPG, PNG, or PDF smaller than 8 MB.");
      return;
    }
    void act(() => api.addCaseEvidence(selectedId, file));
  };

  const download = async (caseId: string, evidenceId: string, filename: string) => {
    try {
      const blob = await api.downloadEvidence(caseId, evidenceId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Download failed"); }
  };

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside className={`cases-drawer ${expanded ? "cases-drawer--expanded" : ""}`} role="dialog" aria-modal="true" aria-label={reviewMode ? "Reports to review" : "My cases"} onClick={(event) => event.stopPropagation()}>
        <header className="cases-head">
          <div>
            <p className="eyebrow">VidhiLens</p>
            <h2>{reviewMode ? "Reports to review" : detail ? "Case details" : "My cases"}</h2>
          </div>
          <div className="cases-head-actions">
            {isAdmin && <button className="button button--ghost" onClick={() => setExpanded((value) => !value)}>{expanded ? "Side view" : "Open full view"}</button>}
            <button className="icon-button" aria-label="Close cases" onClick={onClose}>×</button>
          </div>
        </header>
        <div className="cases-body">
          {error && <p className="inline-error" role="alert">{error}</p>}
          {selectedId && detail ? (
            <>
              <button className="text-action" onClick={() => { setSelectedId(null); setDetail(null); }}>← All cases</button>
              <div className="case-summary">
                <span className="case-status">{(reviewMode ? reviewerStatusNames : statusNames)[detail.status]}</span>
                <h3>{detail.submission.fields.incident_description?.slice(0, 100) || "Case"}</h3>
                <p>VidhiLens reference: <strong>{detail.case_id}</strong></p>
                {detail.reporter_role === "on_behalf" && <p>Reported for <strong>{detail.submission.affected_person_name}</strong> · {detail.reporter_relationship}</p>}
                {detail.verified_phone && <p>Reporter phone verified</p>}
                <p>This record is for VidhiLens review. It is not a police report or FIR.</p>
                {!reviewMode && <button className="text-action" onClick={() => { onOpenSession(detail.session_id); onClose(); }}>Read original conversation</button>}
                {reviewMode && onResearch && <button className="button button--secondary" onClick={() => onResearch(detail)}>Research this report in chat</button>}
              </div>
              <details className="case-disclosure" open={reviewMode}><summary>Read submitted report</summary><pre>{detail.submission.rendered_text}</pre></details>
              <section className="case-timeline" aria-label="Case updates">
                <h3>Updates and messages</h3>
                {[...(detail.events || []).map((item) => ({
                  key: item.event_id, at: item.created_at, kind: "event" as const,
                  text: item.details?.reason || statusNames[item.event_type as ReviewCase["status"]] || item.event_type.replaceAll("_", " "),
                })), ...(detail.messages || []).map((item) => ({
                  key: item.message_id, at: item.created_at, kind: item.actor_role,
                  text: item.text,
                }))].sort((a, b) => a.at.localeCompare(b.at)).map((item) => (
                  <div key={item.key} className={`case-update case-update--${item.kind}`}>
                    <small>{item.kind === "reviewer" ? (reviewMode ? "You" : "VidhiLens reviewer") : item.kind === "citizen" ? (reviewMode ? "Reporter" : "You") : "Status update"} · {new Date(item.at).toLocaleString()}</small>
                    <p>{item.text}</p>
                  </div>
                ))}
              </section>
              <section className="case-files">
                <h3>Evidence</h3>
                {(detail.evidence || []).map((item) => <button key={item.evidence_id}
                  onClick={() => void download(detail.case_id, item.evidence_id, item.filename)}>{item.filename} · {Math.round(item.size / 1024)} KB ↓</button>)}
                {(detail.evidence || []).length === 0 && <p>No files added yet.</p>}
                {detail.status !== "closed" && <>
                  <input ref={fileInput} type="file" accept=".jpg,.jpeg,.png,.pdf" hidden
                    onChange={(event) => { upload(event.target.files?.[0]); event.target.value = ""; }} />
                  <button className="button button--ghost" disabled={busy} onClick={() => fileInput.current?.click()}>Add evidence</button>
                </>}
              </section>
              {detail.status !== "closed" && <form className="case-reply" onSubmit={(event) => {
                event.preventDefault(); if (!reply.trim()) return;
                void act(() => api.sendCaseMessage(detail.case_id, reply.trim())).then((success) => { if (success) setReply(""); });
              }}>
                <label htmlFor="case-message">Message {reviewMode ? "the user" : "the reviewer"}</label>
                <textarea id="case-message" value={reply} onChange={(event) => setReply(event.target.value)}
                  placeholder="Write a clear message…" />
                <button className="button button--primary" disabled={busy || !reply.trim()}>Send message</button>
              </form>}
              {detail.status === "closed" && !reviewMode && <section className="review-actions">
                <h3>Ask us to review this again</h3>
                <p>If you have new information or think something was missed, explain it here. Your request will be added to the case history.</p>
                <label>Why should this case be reviewed again?
                  <textarea value={reviewReason} onChange={(event) => setReviewReason(event.target.value)}
                    placeholder="Describe what changed or what was missed." /></label>
                <button className="button button--primary" disabled={busy || reviewReason.trim().length < 10}
                  onClick={() => void act(() => api.requestCaseReview(detail.case_id, reviewReason.trim())).then((success) => { if (success) setReviewReason(""); })}>Request another review</button>
              </section>}
              {reviewMode && <section className="review-actions">
                <h3>Reviewer decision</h3>
                <label>Action<select value={decision} onChange={(event) => setDecision(event.target.value as typeof decision)}>
                  {decisionNames.filter(([value]) => value === "reopen" ? detail.status === "closed" : detail.status !== "closed")
                    .map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select></label>
                <label>Reason shown in case history<textarea value={reason} onChange={(event) => setReason(event.target.value)}
                  placeholder="Explain what was checked and what the user should do next." /></label>
                <button className="button button--primary" disabled={busy || reason.trim().length < 10}
                  onClick={() => void act(() => api.decideCase(detail.case_id, decision, reason.trim())).then((success) => { if (success) setReason(""); })}>Record decision</button>
              </section>}
            </>
          ) : (
            <>
              {(reviewMode || cases.length + availableDrafts.length > 4) && <div className="case-filters">
                <label>Find a case<input value={caseSearch} onChange={(event) => setCaseSearch(event.target.value)}
                  placeholder="Search by name, incident, or reference" /></label>
                <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="all">All statuses</option>
                  {Object.entries(reviewMode ? reviewerStatusNames : statusNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select></label>
              </div>}
              {!reviewMode && cases.some((item) => item.status === "information_requested") &&
                <p className="case-attention">A reviewer is waiting for your reply.</p>}
              {shownCases.map((item) => <button className="case-list-item" key={item.case_id}
                onClick={() => { setDetail(null); setSelectedId(item.case_id); }}>
                <strong>{item.submission.fields.incident_description?.slice(0, 82) || "Incident report"}</strong>
                <span>{(reviewMode ? reviewerStatusNames : statusNames)[item.status]} · {item.case_id}</span>
                {reviewMode && <small>{item.submission.fields.reporter_name || "Name not given"} · {new Date(item.created_at).toLocaleDateString()}</small>}
              </button>)}
              {shownCases.length === 0 && <p className="cases-empty">{reviewMode ? "No reports match this view." : "No cases here yet. When you send a report for VidhiLens review, it will appear here."}</p>}
              {!reviewMode && availableDrafts.length > 0 && <section className="draft-list">
                <h3>Drafts</h3>
                {availableDrafts.map((item) => <button className="case-list-item" key={item.draft_id} onClick={() => onOpenDraft(item.draft_id)}>
                  <strong>{item.fields.incident_description?.slice(0, 82) || "Untitled draft"}</strong>
                  <span>{item.status === "saved" ? "Saved draft" : "Needs review"}</span>
                </button>)}
              </section>}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
