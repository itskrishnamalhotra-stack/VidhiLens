export type Outcome = "provision_match" | "insufficient_information" | "out_of_scope";

export interface Provision {
  provision_id: string;
  title: string;
  legal_status: string;
  verified_text: string;
  source_url: string;
  source_pdf_page?: number | null;
}

export interface UncertainSection {
  provision_id: string;
  title: string;
  missing_facts: string;
  options: string[];
}

export interface Analysis {
  outcome: Outcome;
  possible_provision_ids: string[];
  provisions: Provision[];
  uncertain_sections: UncertainSection[];
  can_prepare_draft: boolean;
  pipeline_id: string;
  model_version: string;
  kb_version: string;
  notice: string;
  timing?: { total_seconds?: number };
}

export interface AssistantStructured {
  action: "offer_draft" | "ask_question" | "refer_to_authorities" | "conversation" | "review_draft" | "review_research" | "collect_draft_details";
  draft_id?: string;
  analysis?: Analysis;
  analysis_id?: string | null;
  next_question?: { text: string; options: string[] } | null;
  conversation_kind?: "greeting" | "help" | "thanks" | "wellbeing" | "identity" |
    "acknowledgement" | "confusion" | "goodbye" | "apology" | "filing" |
    "distress" | "casual" | "unclear";
  suggestions?: Array<{ label: string; prefill: string }>;
  draft_is_local_only: boolean;
  official_filing_performed: boolean;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  structured?: AssistantStructured | null;
  created_at: string;
}

export interface Session {
  session_id: string;
  owner_uid: string;
  title: string;
  status: string;
  active_narrative: string;
  created_at: string;
  updated_at: string;
  messages?: Message[];
}

export type DraftStatus = "preview" | "needs_reanalysis" | "saved" | "cancelled";

export interface ComplaintDraft {
  draft_id: string;
  session_id: string;
  analysis_id: string;
  fields: Record<string, string>;
  provision_ids: string[];
  rendered_text: string;
  version: number;
  status: DraftStatus;
  internal_reference?: string | null;
  filing_notice?: string;
  created_at: string;
  updated_at: string;
}

export interface MessageTurn {
  user_message: Message;
  assistant_message: Message;
  analysis_id: string | null;
}

export interface RuntimeConfig {
  apiBaseUrl?: string;
}

export type CaseStatus = "submitted" | "information_requested" | "under_review" |
  "ready_to_refer" | "out_of_scope" | "closed";

export interface ReviewCase {
  case_id: string;
  draft_id: string;
  session_id: string;
  owner_uid: string;
  status: CaseStatus;
  reporter_role: "self" | "witness" | "on_behalf";
  reporter_relationship: string;
  verified_phone: string | null;
  submission: {
    fields: Record<string, string>;
    provision_ids: string[];
    rendered_text: string;
    draft_version: number;
    affected_person_name?: string;
  };
  created_at: string;
  updated_at: string;
  filing_notice?: string;
  events?: Array<{ event_id: string; actor_uid: string; event_type: string; details: { reason?: string }; created_at: string }>;
  messages?: Array<{ message_id: string; actor_uid: string; actor_role: "citizen" | "reviewer"; text: string; created_at: string }>;
  evidence?: Array<{ evidence_id: string; filename: string; content_type: string; sha256: string; size: number; created_at: string }>;
}

export interface MyIdentity {
  uid: string;
  is_admin: boolean;
  phone_verified: boolean;
  demo_mode: boolean;
}
