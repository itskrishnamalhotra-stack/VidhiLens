# Phase 1 — law database and first release scope

Owner: Krishna Malhotra. Model training will be done in Google Colab in Phase 3.

## Latest trainer files (19 September 2026)

Step 1 positive-example review is complete at the AI-reviewed research level.
The current complaint-only candidate is
`exports/complaint_training_v10_step2_research_candidate/` with **4,538 train**
and **60 development** records. The current optional Q&A mixture is
`exports/mixed-source-v21-step2-nyaya-experiment/` with **8,107 train** and
**60 development** records. The master database points to these versions and
keeps **55 sealed** cases separate. Read [Step 1 completion](STEP1_POSITIVE_COMPLETION.md)
and [Step 2 completion](STEP2_COMPLETION.md) for the audits, corrections, and
remaining quality limits. The version numbers below describe the earlier
dataset snapshots as they were built.

## Current status (19 September 2026)

The 483-section BNS/IT Act index contains 297 entries currently classified as
in-force offences with verified text. The 19-section recommendation gate is
unchanged. Every one of the 297 now has at least two positive train-format
research complaints and at least one missing-fact triage complaint. All 297
also have an uncertain and an unsupported section-conditioned training check;
11 extra comparisons cover commonly confused sections. This completes the
missing-fact and difficult-case dataset step at AI-authored research level.
See [Part 2 completion](PART2_COMPLETION.md) and
`review_automation/part2_final_v1/summary.json` for exact evidence and limits.

The current unified complaint-training candidate is
`exports/complaint_training_v8_research_candidate/`: 4,523 train records
(3,866 triage, 52 workflow, 605 candidate checks) and 60 development records
(57 triage, 3 workflow). No sealed case is in this bundle. The full research
mixed research experiment is `exports/mixed-source-v17-complaint-gsms-research/`: 5,945 train, 60
development, and 55 additional sealed cases indexed in
`db/master_dataset.sqlite`. All 5,259 Nyaya v3 train and 280 development legal
Q&A rows received a full mechanical screen and were held from this core export;
the prior v15 research export preserves them for later targeted answer review.
The 1,422 GSMS BNS explanatory Q&A rows passed automated source/status checks
and remain tagged as auxiliary research training, not verified complaint labels.
The experiment combines the 4,523-record complaint v8 train bundle with those
1,422 Q&A rows; the complaint-only bundle remains the baseline. The master database pins
hash-checked compressed copies of the current bundle and its source ledgers.

A separate Nyaya Q&A training experiment is now in
`exports/mixed-source-v18-nyaya-screened-experiment/`: **6,932 train and 60
development** records, including **987** added Nyaya BNS/IT grounded Q&A rows.
The original 5,539 Nyaya rows did not pass whole-set sampling: an IT Act
answer used an obsolete Section 45 penalty. See
[the Nyaya training screen](NYAYA_QA_TRAINING_SCREEN_20260919.md) for selection,
exclusions, verified-context rewriting and checks. The v17 bundle remains the
comparison run; v18 is an optional Colab training input, not a deployed model.

The follow-up bulk review added **1,160** BNSS/BSA grounded Q&A rows after
screening their supplied passages against Ministry of Home Affairs Gazette
PDFs. The resulting `exports/mixed-source-v19-nyaya-bnss-bsa-experiment/` has
**8,092 train and 60 development** records, including **2,147 Nyaya Q&A**.
The other **3,392 Nyaya rows** remain outside training (3,112 publisher train
held and 280 publisher development held). See
[the remaining-row review](NYAYA_REMAINING_FAST_REVIEW_20260919.md) for reasons
and checks. This is a separate Colab experiment; v17 and v18 remain available
for comparison on the same complaint evaluation cases.

The independent development/sealed evaluation cases for 256 sections remain
Part 3. Count coverage and AI-only source review do not prove legal accuracy or
model reliability. Colab training follows dataset completion, then interactive
Colab testing, endpoint evaluation, and UI development.

## Historical snapshot (17 September 2026)

1. The database contains **358 BNS section entries** and **125 IT Act section entries** from pinned India Code PDFs. This is a complete section index of those snapshots, not a claim that all 483 entries have been legally reviewed. **67 entries have source-checked text.** The Act-wide BNS commencement notice resolved commencement status for 325 more sections without approving their extracted text. The remaining review queue has 400 entries: 311 need text and kind review, and 89 still have pending legal status.
2. The first release scope has 20 priority offence sections. Their source pages and cleaned text hashes are in `priority_source_audit.json`. **19 are enabled** in the `recommendable_provision` view for this academic prototype; **IT Act 66E is held** because the India Code consolidation prints “public area” in its definition while another official reproduction prints “pubic area.” Do not silently change either text.
3. BNS 114 and 116, and IT Act 43 were source checked as supporting provisions. They do not appear as standalone offence suggestions. Two IT Act expansion batches and three BNS batches added source-checked text for another 44 entries; these are **not yet recommendable** because complaint labels, exceptions and workflow coverage remain incomplete. BNS 86 defines the cruelty term used in BNS 85.
4. The older IT Act PDF is retained for history only. The current India Code consolidation and [MeitY's Jan Vishwas memorandum](https://www.meity.gov.in/static/uploads/2024/03/MeitY-JVA-1.pdf) establish that IT Act 66A was omitted and 72A became a civil penalty from 30 November 2023. Both are blocked from criminal complaint recommendations. Fifteen more IT Act entries explicitly marked "Omitted" in the pinned PDF are now recorded as omitted and blocked. The [MHA BNS commencement notification](https://www.mha.gov.in/sites/default/files/BhartiyaNyayaSanhita_24022024.pdf) excludes BNS 106(2) from the 1 July 2024 commencement.
5. Six public dataset files are downloaded with licence, revision and hash records. They remain quarantined until example by example legal and privacy review. No public data has been called a gold complaint label.
6. The **single canonical file** is `db/master_dataset.sqlite`. It links law, incidents, facts, labels, conversation actions and source records, and embeds compressed, hash-checked copies of 37 official/public/review/contract artifacts. The `master_training_record` view contains accepted train cases only; dev and sealed test stay in separate views. The application must query only `recommendable_provision` for section suggestions.
7. Research and data preparation are documented in `DATA_INVENTORY.md`, `PUBLIC_DATA_SHORTLIST.md`, `RESEARCH_DECISIONS.md`, `LABELING_GUIDE.md`, `AI_REVIEW_PROTOCOL.md`, `EXTERNAL_TRIAGE_QUALITY.md`, `dataset_contract.json`, `EVALUATION_PLAN.md`, `DEPLOYMENT_ARCHITECTURE.md`, `PAPER_EVIDENCE_PLAN.md`, and `PREBUILD_HANDOFF.md`. The original 161-row screening queue had 57 fictional drafts and 104 quarantined public candidates. The reviewed fictional set now has **250 accepted incidents** split **193 train / 24 dev / 33 sealed test**, plus four superseded rejected rows retained for audit. It includes **160 possible matches and 90 abstentions**. There are **49 reviewed structured fact rows** and **32 reviewed conversation actions**. The pilot split passes mechanical audits, but the final dataset and full law review are incomplete.

## Scope and limits

This is an AI assisted source audit of **central Act snapshots** for an academic prototype, not a legal opinion or a live legal service. It does not certify state amendments, later changes, case law, police procedure or factual application to a real complaint. Recheck the law and obtain qualified legal review before real world deployment. The **464 entries outside the 19-section recommendation gate** remain an index or source-review material, not approved suggestions. A printed consolidation date is absent from the current IT Act PDF; its Jan Vishwas changes were cross checked against MeitY.

## How to reproduce and check

On the existing reviewed database, run:

```text
python phase1/scripts/validate_kb.py
python phase1/scripts/audit_full_law_index.py
python phase1/scripts/report_data_readiness.py
python phase1/scripts/audit_dataset.py
python phase1/scripts/audit_research_coverage.py
python phase1/scripts/verify_research_master.py
python phase1/scripts/audit_research_split_leakage.py
```

`process_coverage_batch.py --source phase1/data_drafts/coverage_batchNN.json`
runs the checks, appends a versioned research export, audits coverage and
leakage, and syncs the master database. It refuses duplicate case IDs already
in the export. `sync_research_export_to_master.py` can also import a checked
research export into the SQLite research table. Its default points to the
current v17 export. The verifier reconstructs the train and development JSONL files from SQLite and
checks their hashes against the frozen manifest. It also confirms the 55
additional sealed records remain in a separate database view.
The lexical split screen found zero exact matches and zero similarities at or
above 0.75 among 57 development and 133 sealed complaint cases compared with
4,132 train complaint cases in the full research inventory. This does not rule
out semantic or family leakage. Run `verify_part2_final.py` for the complaint
training bundle, per-section fact gaps, candidate checks, and pinned artifacts.

For a **fresh copy**, run `build_full_kb.py`, `review_priority.py`, `migrate_dataset_model.py`, `migrate_ai_review_tier.py`, `mark_explicit_it_omissions.py`, and `apply_bns_commencement_review.py` in order. Then run `review_it_expansion_batch01.py` and `review_it_expansion_batch02.py`, and import both `bns_offence_review_batch*.jsonl` ledgers with `import_law_review_batch.py`. Import the three `seed_review_batch*.jsonl` ledgers, `fact_review_batch01.jsonl`, `followup_review_batch01.jsonl`, and `workflow_review_batch01.jsonl` with their matching importers. Import both `rich_candidates_batch*.jsonl` with their paired `rich_review_batch*.jsonl` via `import_rich_review_batch.py`, apply the two supersession scripts, and import their dev/test replacement candidate and review ledgers. Finally import `fact_review_batch02.jsonl`, `workflow_review_batch02.jsonl` and `workflow_review_batch03.jsonl`, import `bulk_review_batch03.jsonl`, `hinglish_review_batch04.jsonl`, and `hindi_review_batch05.jsonl` each as both candidate and review input to `import_rich_review_batch.py`, and run `consolidate_master_dataset.py` to embed the pinned artifacts. The builder verifies pinned source hashes and section counts and refuses to replace the reviewed database. The validator checks source files, text hashes, review audits and recommendation gates. The full-index audit flags mechanical extraction risks but does not verify legal status. `export_colab_data.py` remains closed until the final dataset target and audits pass; its default export then contains train/dev only and withholds the sealed test.

## Next phase

Part 3 is independent development and sealed-test complaints, including
confusing alternatives and missing facts. Part 4 is the separate legal-Q&A
quality screen and task-mixture decision. Model training then takes place in
Google Colab before endpoint and UI work.
