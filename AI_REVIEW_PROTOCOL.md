# AI-only dataset review protocol

Owner: Krishna Malhotra. Reviewer: Codex AI. Decision dated 16 September 2026. No human review is planned for the academic dataset. Do not describe this process as professional legal validation.

## Review every candidate in separate passes

1. **Source and privacy pass:** verify the row ID, licence or project-created origin, text hash, fictional/non-identifying content, coherent facts, duplicates and language. Reject or redact an unsafe candidate with an explicit reason; keep the original source record in quarantine.
2. **Legal pass:** compare only stated facts with the pinned, currently eligible official provision text. Record factual support, missing or contradicted elements, possible/uncertain/unsupported labels, the most useful follow-up question, and a source provision/page. Never accept a publisher's label simply because it appears in a dataset.
3. **Challenge pass:** reconsider the strongest alternative provision and a no-match/insufficient-information outcome. Check whether the first label depended on an invented detail, stale section, exception or legal status. Hold unresolved cases rather than forcing agreement.
4. **Workflow pass:** for selected incidents, review follow-up choices, draft/edit/cancel/confirm examples against `WORKFLOW_SPEC.md`. A selected user option is reported information, not verified evidence; a draft save requires explicit confirmation.
5. **Audit:** store `review_tier=ai_reviewed`, reviewer/date, rationale, source ID, outcome and privacy decision. Run the database audit, duplicate/leakage checks and section-allowlist validation before export.

## What the AI-only test can establish

The unseen set can measure whether the app agrees with the separately recorded AI reference labels, obeys source/consent gates, and works across sessions/users. It cannot establish true legal accuracy in the field. The term paper must say the reference labels were created and checked by AI without a lawyer or other human reviewer. A later real-world service would need qualified human legal review before making stronger claims.

## Current count and review tiers

The master has **3,084 accepted scenarios: 2,980 train, 24 dev, 80 sealed test**. Of these, 324 cases are individually AI-reviewed. The newer 2,760 train-only `silver` rows come from 115 AI-authored and source-checked fact-pattern families, each with 24 actor/report-frame variants. The family is the real unit of legal review; the variants received automated consistency, source-page, privacy-shape, duplicate, and split checks. Do not describe them as 2,760 independent incidents or as individually lawyer-validated labels. They are suitable for a controlled pilot experiment, with their review tier and family group retained in the SFT sidecar.

The limited 19-section pilot export has **3,022 train SFT records**: 2,980 triage and 42 workflow. It has 24 dev records; 80 sealed-test scenarios stay local. The 104 public BNS triage candidates had 21 individually corrected and accepted, while 83 were held. Other downloaded public rows and publisher labels remain quarantined. Passing the row-count target does not prove model quality; evaluate on distinct unseen fact patterns and report the limits of AI-only review.
