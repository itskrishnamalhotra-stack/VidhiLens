# Where the Phase 1 data lives

Owner: Krishna Malhotra. Snapshot: 17 September 2026. A limited trainer-format pilot export exists; no model has been trained.

## The authoritative dataset

There is **one joined SQLite database**, `db/master_dataset.sqlite`. It is the authoritative local master, not a separate law database plus an unrelated complaint database. It contains the linked law/case records and 17,573 downloaded rows as queryable source records. The first 6,681 public rows have compressed, hash-checked source copies inside the database; the 10,892 newly indexed rows have pinned original files and SHA-256 values in `additional_candidates_manifest.json`. Training eligibility comes only from review status.

| Data | Table or view | Current count / rule |
| --- | --- | --- |
| BNS and IT Act index | `provision`, linked to `act` and `source_snapshot` | 358 BNS + 125 IT Act entries; 82 source-checked texts; 81 pending status review and 304 in-force sections still awaiting text review |
| Allowed complaint suggestions | `recommendable_provision` view, with `blocked_provision` | 19 approved sections; the view enforces the gate |
| Complaint incidents | `scenario` | 3,084 accepted: 324 individually AI-reviewed cases plus 2,760 family-reviewed synthetic train variants; four rejected superseded rows remain for audit |
| Complaint-to-law judgments | `scenario_provision_label` | `possible`, `uncertain`, or `unsupported` with AI review records |
| Stated or missing facts | `scenario_fact` | 49 reviewed fact rows |
| Guided conversation examples | `conversation_example` | 53 accepted action turns |
| Supporting law and exceptions | `provision_relation`, `provision_subpart_status` | Cross references and special status records |
| Pinned source and review material | `dataset_artifact`, `dataset_artifact_blob` | 57 embedded source, review, screen and packet artifacts, including the synthetic training CSV; each is hash checked |
| Downloaded rows and review decisions | `public_candidate_row`, `public_candidate_review`, `public_source_screen` | 6,681 indexed and screened source rows; 104 in-scope triage rows reviewed in one batch: 21 corrected and accepted, 83 held |
| New downloaded candidate rows | `additional_candidate_source`, `additional_candidate_row` | 10,892 indexed rows from eight files; all quarantined from training; see `ADDITIONAL_DATASET_AUDIT_20260917.md` |
| Official IPC/BNS correspondence candidates | `ipc_bns_crosswalk_candidate` | 502 reciprocal links from NCRB Sankalan; zero approved as converted training labels. Several IPC sections have more than one BNS candidate. |
| Dataset ownership and safe-use rules | `master_dataset_info` | Owner, version, scope, training and quarantine rules travel with the file |
| Training-only view | `master_training_record` | 2,980 train incidents: 220 individually AI-reviewed plus 2,760 silver variants; no dev or sealed cases |
| Section coverage | `master_section_coverage` | Train, dev and sealed-test positive counts for each currently recommendable section |

Accepted incidents are **2,980 train, 24 development, and 80 sealed test**. The train split includes 2,760 silver variants from **115 distinct fact-pattern families**. Their actor and reporting frame change, while the core legal facts are shared. These rows are not 2,760 independently reviewed incidents. The entire set contains 2,357 provision matches, 431 insufficient-information cases, and 296 out-of-scope cases. It covers the 19-section academic prototype, not every BNS/IT Act offence. Counts should be checked against `data_readiness_report.json` after further imports.

## Other files and what they mean

1. `sources/` contains the pinned official PDFs. `sources_manifest.json` and source hashes record which editions were read. The database connects each provision to its source snapshot and PDF page.
2. `data_drafts/` contains candidate and AI review ledgers, including `bulk_review_batch03.jsonl` (100 accepted train cases). The word *drafts* in this directory name refers to the input ledgers; accepted rows are imported into the SQLite database. The ledgers preserve how decisions were made and can rebuild the database.
3. `external_candidates/` contains the original six downloaded third-party files plus eight newer files under `additional_20260917/`. All 17,573 rows are indexed in the master database. Original file hashes are pinned in `external_candidates_manifest.json` and `additional_candidates_manifest.json`. Publisher labels remain **quarantined** unless separately corrected and reviewed. Of the 104 in-scope triage rows, 21 were individually corrected and source-checked for training, while 83 were held. None of the new 10,892 rows has been promoted.
   `scripts/assemble_master_data.py --sample 100` and `--full` screen the source pool and check the current SFT shape. The full report is `data_drafts/automation_full_report.json`. Screening approves no new training rows; it is an organizing step, not the final case-generation and legal-review stage.
4. `dataset_audit_report.json`, `data_readiness_report.json`, and `full_law_index_audit.json` are generated checks and counts. Read these before trusting a number in a narrative document.
5. `master_training_record` gives one queryable training-only row per accepted train incident. `export_colab_data.py` will later package accepted train/dev rows for Colab while withholding sealed test rows. Its gate currently refuses export because the final law and data work is incomplete. **Do not upload the entire master database to a training notebook**: it contains sealed test cases. Export only the eligible split after the gate passes.
6. `data_drafts/synthetic_training_expansion_v1.csv` is the inspectable, one-batch synthetic training addition: 2,760 rows in 115 fact-pattern families. It was imported once by `scripts/import_training_expansion_csv.py` and marked `review_tier=silver`. Its contents are AI-authored fictional examples, not public complaints or legal validation. `exports/scoped-pilot-20260917T140833Z/` contains the latest trainer-compatible **limited 19-section pilot**: 3,022 train SFT records (2,980 triage and 42 workflow) and 24 development records. The 80 sealed-test scenarios remain local. Earlier pilot exports remain historical snapshots.
7. `master_v1_verification.json` is the repeatable integrity result from `scripts/verify_master_v1.py`. It checks all 6,681 row hashes, every embedded artifact, SQLite foreign keys, split separation, pilot export hashes and JSON shape. Passing this check means the stored data is internally consistent; it does not certify the unreviewed legal content or publisher labels.

The public `ri2000/Complaint_and_Sections` card advertises 47,329 complaint/IPC pairs, but the files require an access grant. No rows from that source are included or counted here. IPC labels would need individual legal mapping and review before any BNS use.
The official NCRB Sankalan IPC/BNS correspondence page is pinned in the master, with 502 reciprocal parsed candidate pairs. Its mappings speed up *candidate retrieval* when the restricted IPC complaint set becomes available. They never convert complaint labels automatically; the actual facts and changed legal elements still need review.
When access is granted, put the downloaded `.jsonl` or `.json` file under `external_candidates/` and run `python scripts/preflight_ipc_complaints.py external_candidates/<filename>` from the `phase1` directory. This local, read-only intake writes only hashed row diagnostics and counts; it does not copy complaint text into its reports or approve training labels. Large `.json` arrays need the optional `ijson` package for streaming. The two-row fictional smoke check passed and was removed.

## Simple rule for future imports

A public file or a newly written line does not become training data merely by existing on disk. It becomes an accepted row only after provenance, privacy, legal label, duplicate, split, and review checks pass and it is imported into `db/master_dataset.sqlite`. Keep the original source and review reason. Do not move rows between splits to improve a reported score.

## What is still weak

- The 81 pending-status entries and 304 in-force sections without verified text block a claim of full BNS/IT Act coverage. Eight IT Act amendment sections now have source-checked commencement status from the MeitY memorandum, with text and kind still pending. Fifteen BNS sections on official PDF pages 83–85 were visually checked and source-approved without enabling complaint suggestions. The bulk BNS commencement review used the Act-wide official notice; it did not verify each other section's wording or kind, and section 106(2) remains excepted. The remaining source-review queue has 385 entries.
- The numerical 3,000-record target is met, but 2,760 of 3,022 train SFT records are surface variants of 115 fact-pattern families. The distinct legal situations and natural language are still much thinner than the row count suggests. This batch has no new IT Act 65 positive cases because that section requires a specific legal duty to retain source code. Thirty cases use Romanized Hindi and 20 use Devanagari; both need more natural variation. A later training run must measure held-out performance before deciding whether this dataset is adequate.
- Fifty-three conversation turns exist across all splits. Forty-two are in the training split; each supported action has at least three reviewed train examples. This is an inspection floor, not evidence that the final workflow will work reliably. The sealed-test turns never go into Colab training.
- The 300-case planning target is a **minimum research milestone**, not assurance of a full-coverage AI. Coverage and held-out error results must determine when enough examples exist.
