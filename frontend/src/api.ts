import type { ComplaintDraft, MessageTurn, MyIdentity, ReviewCase, Session } from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    const message = typeof detail === "string" ? detail
      : detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string"
        ? detail.message : "The request could not be completed";
    const analysis = detail && typeof detail === "object" && "analysis" in detail ? detail.analysis : null;
    const missingFact = analysis && typeof analysis === "object" && "uncertain_sections" in analysis &&
      Array.isArray(analysis.uncertain_sections) && typeof analysis.uncertain_sections[0]?.missing_facts === "string"
        ? analysis.uncertain_sections[0].missing_facts : null;
    super(missingFact ? `${message}. If you know, clarify: ${missingFact}` : message);
    this.status = status;
    this.detail = detail;
  }
}

export class LegalAiApi {
  constructor(
    private readonly baseUrl: string,
    private readonly getAuthHeaders: () => Promise<Record<string, string>>,
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const auth = await this.getAuthHeaders();
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...auth,
        ...(init.headers || {}),
      },
    });
    if (!response.ok) {
      let detail: unknown = `Request failed (${response.status})`;
      try {
        const body = await response.json();
        detail = body.detail ?? detail;
      } catch {
        // Keep the status-based message.
      }
      throw new ApiError(response.status, detail);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  health() {
    return fetch(`${this.baseUrl}/health?deep=true`).then((response) => response.json());
  }

  listSessions() {
    return this.request<Session[]>("/sessions");
  }

  createSession(title: string) {
    return this.request<Session>("/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  }

  getSession(sessionId: string) {
    return this.request<Session>(`/sessions/${sessionId}`);
  }

  removeSession(sessionId: string) {
    return this.request<{ outcome: "deleted" | "archived" }>(`/sessions/${sessionId}`, { method: "DELETE" });
  }

  sendMessage(sessionId: string, text: string, startNewIncident = false) {
    return this.request<MessageTurn>(`/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ text, start_new_incident: startNewIncident }),
    });
  }

  createDraft(sessionId: string, details: Record<string, string> = {}) {
    return this.request<ComplaintDraft>("/drafts", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, details }),
    });
  }

  getDraft(draftId: string) {
    return this.request<ComplaintDraft>(`/drafts/${draftId}`);
  }

  listDrafts() {
    return this.request<ComplaintDraft[]>("/drafts");
  }

  patchDraft(draftId: string, expectedVersion: number, changes: Record<string, string>) {
    return this.request<ComplaintDraft>(`/drafts/${draftId}`, {
      method: "PATCH",
      body: JSON.stringify({ expected_version: expectedVersion, changes }),
    });
  }

  reanalyzeDraft(draftId: string, expectedVersion: number) {
    return this.request<ComplaintDraft>(`/drafts/${draftId}/reanalyze`, {
      method: "POST",
      body: JSON.stringify({ expected_version: expectedVersion }),
    });
  }

  confirmDraft(draftId: string, expectedVersion: number) {
    return this.request<ComplaintDraft>(`/drafts/${draftId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ expected_version: expectedVersion, explicit_confirmation: true }),
    });
  }

  cancelDraft(draftId: string, expectedVersion: number) {
    return this.request<ComplaintDraft>(`/drafts/${draftId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ expected_version: expectedVersion }),
    });
  }

  deleteDraft(draftId: string) {
    return this.request<void>(`/drafts/${draftId}`, { method: "DELETE" });
  }

  me() { return this.request<MyIdentity>("/me"); }
  listCases() { return this.request<ReviewCase[]>("/cases"); }
  getCase(caseId: string) { return this.request<ReviewCase>(`/cases/${caseId}`); }
  submitCase(draftId: string, reporterRole: string, reporterRelationship: string, affectedPersonName: string) {
    return this.request<ReviewCase>("/cases", {
      method: "POST", body: JSON.stringify({
        draft_id: draftId, reporter_role: reporterRole,
        reporter_relationship: reporterRelationship, affected_person_name: affectedPersonName,
        declaration_accepted: true,
      }),
    });
  }
  sendCaseMessage(caseId: string, text: string) {
    return this.request<ReviewCase["messages"]>(`/cases/${caseId}/messages`, {
      method: "POST", body: JSON.stringify({ text }),
    });
  }
  requestCaseReview(caseId: string, reason: string) {
    return this.request<ReviewCase>(`/cases/${caseId}/review-request`, {
      method: "POST", body: JSON.stringify({ reason }),
    });
  }
  async addCaseEvidence(caseId: string, file: File) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    }
    return this.request<ReviewCase["evidence"]>(`/cases/${caseId}/evidence`, {
      method: "POST", body: JSON.stringify({
        filename: file.name, content_type: file.type, data_base64: btoa(binary),
      }),
    });
  }
  listReviewCases() { return this.request<ReviewCase[]>("/review/cases"); }
  decideCase(caseId: string, action: string, reason: string) {
    return this.request<ReviewCase>(`/review/cases/${caseId}/decision`, {
      method: "POST", body: JSON.stringify({ action, reason }),
    });
  }
  evidenceUrl(caseId: string, evidenceId: string) {
    return `${this.baseUrl}/cases/${caseId}/evidence/${evidenceId}`;
  }
  async downloadEvidence(caseId: string, evidenceId: string): Promise<Blob> {
    const auth = await this.getAuthHeaders();
    const response = await fetch(this.evidenceUrl(caseId, evidenceId), { headers: auth });
    if (!response.ok) throw new ApiError(response.status, "Could not download evidence");
    return response.blob();
  }
}

