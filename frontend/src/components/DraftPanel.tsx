import { useEffect, useMemo, useState } from "react";
import type { ComplaintDraft } from "../types";
import { Icon } from "./Icon";
import { PhoneVerification } from "./PhoneVerification";
import { useAuth } from "../auth";

const fieldDefinitions = [
  ["reporter_name", "Your name"],
  ["contact", "Contact details"],
  ["incident_date", "Incident date"],
  ["incident_time", "Incident time"],
  ["location", "Location"],
  ["incident_description", "Incident description"],
  ["property_or_account", "Property or account involved"],
  ["accused_details", "Person complained about"],
  ["witnesses", "Witnesses"],
  ["evidence", "Available evidence"],
  ["requested_action", "Requested action"],
] as const;

interface Props {
  draft: ComplaintDraft;
  busy: boolean;
  error: string;
  onClose: () => void;
  onCancel: () => Promise<void>;
  onDelete: () => Promise<void>;
  onSubmitCase: (reporterRole: "self" | "witness" | "on_behalf", relationship: string, affectedPersonName: string) => Promise<void>;
  onAdvance: (changes: Record<string, string>, destination: "send" | "later") => Promise<boolean>;
  alreadySubmitted: boolean;
}

export function DraftPanel({ draft, busy, error, onClose, onCancel, onDelete, onSubmitCase, onAdvance, alreadySubmitted }: Props) {
  const auth = useAuth();
  const [fields, setFields] = useState(draft.fields);
  const [preview, setPreview] = useState(false);
  const [copied, setCopied] = useState(false);
  const [reporterRole, setReporterRole] = useState<"self" | "witness" | "on_behalf">("self");
  const [relationship, setRelationship] = useState("");
  const [affectedPersonName, setAffectedPersonName] = useState("");
  const [declared, setDeclared] = useState(false);
  const [step, setStep] = useState<"edit" | "send">("edit");
  useEffect(() => setFields(draft.fields), [draft]);

  const changes = useMemo(() => Object.fromEntries(
    Object.entries(fields).filter(([key, value]) => value !== (draft.fields[key] || ""))
  ), [fields, draft.fields]);

  const copy = async () => {
    await navigator.clipboard.writeText(draft.rendered_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };
  const close = () => {
    if (Object.keys(changes).length > 0 && !window.confirm("Close without saving these draft edits?")) return;
    onClose();
  };
  const advance = async (destination: "send" | "later") => {
    const succeeded = await onAdvance(changes, destination);
    if (succeeded) {
      if (destination === "send") { setStep("send"); setPreview(true); }
      else onClose();
    }
  };

  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="draft-drawer" role="dialog" aria-modal="true" aria-label="Complaint draft">
        <header className="draft-head">
          <div>
            <p className="eyebrow">{step === "send" ? "Final step · send for internal review" : "Step 1 · review your report"}</p>
            <h2>{step === "send" ? "Review and send" : "Review your complaint draft"}</h2>
            <div className="draft-meta">
              <span>Version {draft.version}</span>
              <span className={`status-pill status-pill--${draft.status}`}>{draft.status.replace("_", " ")}</span>
            </div>
          </div>
          <button className="icon-button" onClick={close} aria-label="Close draft"><Icon name="close" /></button>
        </header>

        {error && <p className="inline-error draft-inline-error" role="alert">{error}</p>}

        {draft.status === "saved" && (
          <div className="saved-banner">
            <Icon name="check" />
            <div><strong>Draft saved · not sent for review</strong><span>Reference {draft.internal_reference}</span></div>
          </div>
        )}
        {draft.status === "needs_reanalysis" && (
          <div className="review-banner">
            <Icon name="spark" />
            <div><strong>Legal facts changed</strong><span>Recheck the possible provisions before confirming this version.</span></div>
          </div>
        )}

        {step === "edit" && <div className="draft-tabs">
          <button className={!preview ? "active" : ""} onClick={() => setPreview(false)}>Details</button>
          <button className={preview ? "active" : ""} onClick={() => setPreview(true)}>Full preview</button>
        </div>}

        <div className="draft-body">
          {step === "send" ? (
            <div className="final-report-summary">
              <p className="draft-section-title">Check the report you are sending</p>
              <strong>{draft.fields.incident_description || "Incident details not provided"}</strong>
              <span>{draft.fields.reporter_name || "Add your name before sending"} · {draft.fields.incident_date || "Date not supplied"} · {draft.fields.location || "Location not supplied"}</span>
              <details className="case-disclosure"><summary>Read the full report</summary><pre>{draft.rendered_text}</pre></details>
            </div>
          ) : preview ? (
            <div className="draft-preview">
              {Object.keys(changes).length > 0 && <p className="review-banner">Your recent edits will appear in this preview after you continue.</p>}
              <button className="copy-button" onClick={copy}><Icon name={copied ? "check" : "copy"} />{copied ? "Copied" : "Copy"}</button>
              <pre>{draft.rendered_text}</pre>
            </div>
          ) : (
            <div className="draft-form">
              <p className="draft-section-title">About you and the incident</p>
              {fieldDefinitions.slice(0, 6).map(([key, label]) => (
                <label key={key} className={key === "incident_description" || key === "evidence" ? "span-2" : ""}>
                  {label}
                  {key === "incident_description" || key === "evidence" || key === "requested_action" ? (
                    <textarea value={fields[key] || ""} disabled={alreadySubmitted || draft.status === "cancelled"}
                      placeholder={key === "incident_description" ? "What happened? Include only facts you know." : undefined}
                      onChange={(event) => setFields({ ...fields, [key]: event.target.value })} />
                  ) : (
                    <input value={fields[key] || ""} disabled={alreadySubmitted || draft.status === "cancelled"}
                      placeholder={key === "location" ? "City, area or college" : key === "contact" ? "A way to contact you" : undefined}
                      onChange={(event) => setFields({ ...fields, [key]: event.target.value })} />
                  )}
                </label>
              ))}
              <details className="draft-more span-2"><summary>Add people, evidence and requested action</summary>
                <div className="draft-form">
                  {fieldDefinitions.slice(6).map(([key, label]) => <label key={key} className={key === "evidence" || key === "requested_action" ? "span-2" : ""}>
                    {label}
                    {key === "evidence" || key === "requested_action" ?
                      <textarea value={fields[key] || ""} disabled={alreadySubmitted || draft.status === "cancelled"}
                        onChange={(event) => setFields({ ...fields, [key]: event.target.value })} /> :
                      <input value={fields[key] || ""} disabled={alreadySubmitted || draft.status === "cancelled"}
                        onChange={(event) => setFields({ ...fields, [key]: event.target.value })} />}
                  </label>)}
                </div>
              </details>
            </div>
          )}
          {step === "send" && draft.status === "saved" && !alreadySubmitted && <section className="submit-review">
            <h3>Send this report to VidhiLens for review</h3>
            <p>A VidhiLens case is an internal review record. This does not file a police complaint or FIR.</p>
            <label>I am reporting
              <select value={reporterRole} onChange={(event) => setReporterRole(event.target.value as typeof reporterRole)}>
                <option value="self">For myself</option><option value="witness">As a witness</option>
                <option value="on_behalf">For someone else</option>
              </select>
            </label>
            {reporterRole === "on_behalf" && <>
              <label>Name of the person affected<input value={affectedPersonName}
                onChange={(event) => setAffectedPersonName(event.target.value)}
                placeholder="Full name if known" /></label>
              <label>My relationship to that person
                <input value={relationship} onChange={(event) => setRelationship(event.target.value)}
                  placeholder="For example, parent or authorised representative" />
              </label>
            </>}
            {auth.user?.mode === "firebase" && <PhoneVerification />}
            <label className="declaration"><input type="checkbox" checked={declared}
              onChange={(event) => setDeclared(event.target.checked)} />
              <span>I have checked this report. The facts are true to the best of my knowledge.</span>
            </label>
            <button className="button button--primary" disabled={busy || Object.keys(changes).length > 0 || !declared || !fields.reporter_name?.trim() ||
              (reporterRole === "on_behalf" && (relationship.trim().length < 5 || affectedPersonName.trim().length < 2)) ||
              (auth.user?.mode === "firebase" && !auth.user.phoneNumber)}
              onClick={() => void onSubmitCase(reporterRole, relationship, affectedPersonName)}>
              Send to VidhiLens for review
            </button>
          </section>}
        </div>

        <footer className="draft-actions">
          <p>{step === "send" ? "Your draft is saved. Sending creates an internal VidhiLens case; it does not file with police." : "This is a draft. It has not been sent to anyone. Continue will take you to the final review and send step."}</p>
          <div>
            {step === "send" && !alreadySubmitted ? (
              <button className="button button--ghost" disabled={busy} onClick={() => { setStep("edit"); setPreview(false); }}>← Edit report</button>
            ) : draft.status === "saved" && !alreadySubmitted ? (
              <>
                <button className="button button--ghost" disabled={busy} onClick={() => void advance("later")}>Save for later</button>
                <button className="button button--danger" disabled={busy} onClick={onDelete}><Icon name="trash" /> Delete draft</button>
                <button className="button button--primary" disabled={busy} onClick={() => void advance("send")}>Continue to review and send →</button>
              </>
            ) : alreadySubmitted ? (
              <span>This submitted report is preserved. Add new information in My cases.</span>
            ) : draft.status === "cancelled" ? null : (
              <>
                <button className="button button--ghost" disabled={busy} onClick={onCancel}>Cancel draft</button>
                <button className="button button--secondary" disabled={busy} onClick={() => void advance("later")}>Save for later</button>
                <button className="button button--primary" disabled={busy} onClick={() => void advance("send")}>Continue to review and send →</button>
              </>
            )}
          </div>
        </footer>
      </aside>
    </div>
  );
}
