PRAGMA foreign_keys = ON;
PRAGMA user_version = 3;

CREATE TABLE act (
    act_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    enactment_year INTEGER NOT NULL
);

CREATE TABLE source_snapshot (
    source_id TEXT PRIMARY KEY,
    act_id TEXT NOT NULL REFERENCES act(act_id),
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    file_path TEXT NOT NULL,
    retrieved_on TEXT NOT NULL,
    printed_as_of TEXT,
    sha256 TEXT NOT NULL UNIQUE
);

CREATE TABLE provision (
    provision_id TEXT PRIMARY KEY,
    act_id TEXT NOT NULL REFERENCES act(act_id),
    section_number TEXT NOT NULL,
    candidate_title TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES source_snapshot(source_id),
    source_pdf_page INTEGER NOT NULL CHECK (source_pdf_page > 0),
    extracted_text TEXT NOT NULL,
    verified_text TEXT,
    provision_kind TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (provision_kind IN ('pending_review', 'offence', 'definition', 'civil_penalty', 'procedure', 'power', 'exception', 'omitted', 'other')),
    legal_status TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (legal_status IN ('pending_review', 'in_force', 'uncommenced', 'struck_down', 'repealed', 'omitted', 'uncertain')),
    text_reviewed_on TEXT,
    status_reviewed_on TEXT,
    reviewed_by TEXT,
    priority_review INTEGER NOT NULL DEFAULT 0 CHECK (priority_review IN (0, 1)),
    recommendable INTEGER NOT NULL DEFAULT 0 CHECK (recommendable IN (0, 1)),
    review_note TEXT,
    UNIQUE (act_id, section_number),
    CHECK (recommendable = 0 OR (
        legal_status = 'in_force' AND provision_kind = 'offence' AND verified_text IS NOT NULL AND
        length(trim(verified_text)) > 0 AND text_reviewed_on IS NOT NULL AND
        status_reviewed_on IS NOT NULL AND reviewed_by IS NOT NULL
    ))
);

CREATE TABLE provision_subpart_status (
    provision_id TEXT NOT NULL REFERENCES provision(provision_id),
    subpart TEXT NOT NULL,
    legal_status TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES source_snapshot(source_id),
    note TEXT NOT NULL,
    PRIMARY KEY (provision_id, subpart)
);

CREATE TABLE blocked_provision (
    provision_id TEXT PRIMARY KEY REFERENCES provision(provision_id),
    reason TEXT NOT NULL
);

CREATE TRIGGER prevent_blocked_recommendation
BEFORE UPDATE OF recommendable ON provision
WHEN NEW.recommendable = 1 AND EXISTS (
    SELECT 1 FROM blocked_provision WHERE provision_id = NEW.provision_id
)
BEGIN
    SELECT RAISE(ABORT, 'blocked provision cannot be recommended');
END;

CREATE TABLE provision_relation (
    from_provision_id TEXT NOT NULL REFERENCES provision(provision_id),
    to_provision_id TEXT NOT NULL REFERENCES provision(provision_id),
    relation_type TEXT NOT NULL CHECK (relation_type IN ('defines', 'cross_references', 'related', 'excludes')),
    note TEXT,
    reviewed_on TEXT,
    PRIMARY KEY (from_provision_id, to_provision_id, relation_type)
);

CREATE TABLE scenario (
    scenario_id TEXT PRIMARY KEY,
    complaint_text TEXT NOT NULL,
    language TEXT NOT NULL,
    provenance_type TEXT NOT NULL CHECK (provenance_type IN ('synthetic', 'public_licensed', 'consented_anonymized')),
    source_url TEXT,
    license TEXT,
    privacy_reviewed INTEGER NOT NULL DEFAULT 0 CHECK (privacy_reviewed IN (0, 1)),
    quality_status TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (quality_status IN ('pending_review', 'accepted', 'rejected')),
    expected_outcome TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (expected_outcome IN ('pending_review', 'provision_match', 'insufficient_information', 'out_of_scope')),
    review_tier TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (review_tier IN ('pending_review', 'ai_reviewed', 'self_reviewed', 'independently_reviewed', 'silver')),
    reviewer TEXT,
    reviewed_on TEXT,
    split TEXT NOT NULL CHECK (split IN ('train', 'dev', 'sealed_test')),
    scenario_group TEXT NOT NULL,
    created_on TEXT NOT NULL,
    review_note TEXT,
    CHECK (quality_status != 'accepted' OR (
        expected_outcome != 'pending_review' AND review_tier != 'pending_review' AND
        reviewer IS NOT NULL AND length(trim(reviewer)) > 0 AND reviewed_on IS NOT NULL AND
        privacy_reviewed = 1 AND (review_tier != 'silver' OR split = 'train')
    ))
);

CREATE TRIGGER scenario_accept_requires_review
BEFORE UPDATE OF quality_status, expected_outcome, review_tier, reviewer, reviewed_on, privacy_reviewed, split ON scenario
WHEN NEW.quality_status = 'accepted' AND (
    NEW.expected_outcome = 'pending_review' OR NEW.review_tier = 'pending_review' OR
    NEW.reviewer IS NULL OR length(trim(NEW.reviewer)) = 0 OR NEW.reviewed_on IS NULL OR
    NEW.privacy_reviewed != 1 OR (NEW.review_tier = 'silver' AND NEW.split != 'train')
)
BEGIN
    SELECT RAISE(ABORT, 'accepted scenario requires outcome, privacy and review evidence');
END;

CREATE TRIGGER scenario_insert_requires_review
BEFORE INSERT ON scenario
WHEN NEW.quality_status = 'accepted' AND (
    NEW.expected_outcome = 'pending_review' OR NEW.review_tier = 'pending_review' OR
    NEW.reviewer IS NULL OR length(trim(NEW.reviewer)) = 0 OR NEW.reviewed_on IS NULL OR
    NEW.privacy_reviewed != 1 OR (NEW.review_tier = 'silver' AND NEW.split != 'train')
)
BEGIN
    SELECT RAISE(ABORT, 'accepted scenario requires outcome, privacy and review evidence');
END;

CREATE TABLE scenario_fact (
    scenario_id TEXT NOT NULL REFERENCES scenario(scenario_id) ON DELETE CASCADE,
    fact_key TEXT NOT NULL,
    fact_value TEXT,
    state TEXT NOT NULL CHECK (state IN ('present', 'absent', 'unknown', 'disputed')),
    evidence_span TEXT,
    PRIMARY KEY (scenario_id, fact_key)
);

CREATE TABLE scenario_provision_label (
    scenario_id TEXT NOT NULL REFERENCES scenario(scenario_id) ON DELETE CASCADE,
    provision_id TEXT NOT NULL REFERENCES provision(provision_id),
    label TEXT NOT NULL CHECK (label IN ('possible', 'unsupported', 'uncertain')),
    rationale TEXT NOT NULL,
    missing_facts TEXT,
    reviewer TEXT,
    reviewed_on TEXT,
    PRIMARY KEY (scenario_id, provision_id)
);

CREATE TABLE conversation_example (
    example_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL REFERENCES scenario(scenario_id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    user_message TEXT,
    assistant_action TEXT NOT NULL CHECK (assistant_action IN (
        'ask_followup', 'suggest_provisions', 'offer_draft', 'draft', 'edit_draft',
        'confirm_draft', 'cancel_draft', 'explain_uncertainty', 'refer_to_authorities'
    )),
    assistant_message TEXT NOT NULL,
    tool_payload_json TEXT,
    quality_status TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (quality_status IN ('pending_review', 'accepted', 'rejected')),
    reviewer TEXT,
    reviewed_on TEXT,
    CHECK (quality_status != 'accepted' OR (reviewer IS NOT NULL AND reviewed_on IS NOT NULL)),
    UNIQUE (scenario_id, turn_index)
);

CREATE VIEW recommendable_provision AS
SELECT provision_id, act_id, section_number, candidate_title, source_id,
       source_pdf_page, verified_text
FROM provision
WHERE recommendable = 1 AND provision_id NOT IN (SELECT provision_id FROM blocked_provision);

CREATE INDEX idx_provision_priority ON provision(priority_review);
CREATE INDEX idx_scenario_split ON scenario(split, quality_status);
CREATE INDEX idx_label_provision ON scenario_provision_label(provision_id, label);
