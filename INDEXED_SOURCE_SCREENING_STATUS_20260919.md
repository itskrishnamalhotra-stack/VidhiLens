# Indexed public-source screening status — 19 September 2026

Owner: Krishna Malhotra. This file distinguishes **indexed**, **mechanically screened**, **answer/label reviewed**, and **selected for an experiment**. An indexed row is searchable provenance, not a correct training point.

## Exact intake inventory

The master SQLite has **17,573** public-source candidate rows: 6,681 in `public_candidate_row` and 10,892 in `additional_candidate_row`. Every one has at least a source-level structural/topic screen or a recorded source disposition. The counts below do not imply 17,573 usable training examples.

| Indexed source | Rows | Screen/disposition | Current training use |
|---|---:|---|---|
| GSMS BNS Q&A | 2,148 | New full-file audit: 2,131 pass mechanical checks, 17 held. Of the passes, 709 scenario/consequence rows stay research-only after a sample showed overconfident or speculative answers. | 1,422 BNS auxiliary Q&A in the core research export, marked `automated_screen_pass_not_semantically_certified`. |
| GSMS BNS structured sections | 358 | Compared against the official-law-backed master text. Formatting/heading differences and the BNS 106(2) commencement caveat are tracked. | Law cross-check only; no complaint examples. |
| Public statutory triage source | 2,219 | Publisher labels rejected at source level after concrete fact-to-law errors. The source review ledger has 242 `accepted_corrected` and 1,278 `held` decisions; remaining rows are excluded at source level rather than individually fact reviewed. | Only separately corrected, reviewed rows may enter task-specific research cases. |
| Nyaya v7 train/validation dialogue | 1,456 | Full structural/domain profile; publisher metadata marks them unverified. | No automatic promotion from this indexed source. |
| Nyaya v7 evaluation | 500 | Profiled and held as external evaluation material; a known BNS 75 answer discrepancy is recorded. | Never put into training. |
| Nyaya v3 train/validation/test | 6,429 | Entire intake mechanically screened. The 5,292 train and 280 validation source files yielded 5,259 train and 280 development Q&A records in the earlier mixed export after initial filtering. A new 5,539-row audit found all had supplied statute passages, 4,168 were outside the project's BNS/IT source-act scope, and 617 lacked a recorded source section. Counts overlap. The 857 publisher test rows remain held. | All 5,539 Q&A records held from the current core experiment; the v15 export and pinned raw source retain them for targeted review. |
| Fraud and cyber safety questions | 2,658 | Full intake screened. Questions can inspire wording, but generated answer citations are not verified fact-to-law labels. | No approved training rows from this source. |
| NariRaksha | 1,000 | Full intake screened; repetitive synthetic templates and concrete wrong section labels identified. | No approved training rows from this source. |
| Complaint-Relevant-BNS | 325 | Full intake screened; generic/section-leaking/pre-commencement rows identified. | No approved training rows from this source. |
| Nyaya statute cross-checks | 480 | 358 BNS and 122 IT rows screened. Its IT text includes a stale 66A offence and lacks some entries in the local index. | Cross-check only; never replace the official law text/status. |

## Current exports

- **Current mixed research experiment:** [`mixed-source-v17-complaint-gsms-research`](exports/mixed-source-v17-complaint-gsms-research/manifest.json), 5,945 train and 60 development rows. It combines the 4,523 complaint v8 train records with 1,422 GSMS auxiliary Q&A rows. The separate 55 sealed research cases remain outside the trainer JSONL. This is a candidate experiment, not a final legal accuracy claim.
- **Previous full mixed inventory:** [`mixed-source-v15-gsms-aux-research`](exports/mixed-source-v15-gsms-aux-research/manifest.json), 10,865 train and 340 development rows. It preserves the 5,539 Nyaya Q&A rows, visibly tagged as publisher material without independent legal answer review.
- **Complaint-only candidate:** [`complaint_training_v8_research_candidate`](exports/complaint_training_v8_research_candidate/manifest.json), 4,523 train and 60 development records. It has no GSMS or Nyaya legal Q&A. Its task is complaint triage/workflow/candidate checking.
- **New Nyaya audit:** [`nyaya_qa_v1`](review_automation/nyaya_qa_v1/summary.json), one audit row per Q&A record, with source metadata, extracted question, and overlapping issue codes.

The current mixed export and master SQLite reproduce each other exactly under [`verify_research_master.py`](scripts/verify_research_master.py). [`verify_part2_final.py`](scripts/verify_part2_final.py) also passes. A fresh [`research_leakage_v17`](review_automation/research_leakage_v17/summary.json) screen found zero exact or ≥0.75 lexical overlaps between 3,866 train triage inputs and 190 development/sealed triage inputs. This screen cannot rule out similar fact patterns written differently.

## Remaining quality work

There is no entire indexed repository that has never been mechanically screened. The meaningful remaining issue is **semantic legal verification**: a structural pass cannot prove that each answer or complaint label follows from the official provision. The 1,422 GSMS auxiliary rows are suitable for a controlled training comparison, but are not gold legal answers. The 709 GSMS scenario/consequence rows and the 5,539 Nyaya Q&A rows require targeted answer review or remain out of core training. Most other public pools have a source-level decision already; bulk promotion would reintroduce known label errors.
