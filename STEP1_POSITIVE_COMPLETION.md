# Step 1: positive complaint review

Owner: Krishna Malhotra. Completed as an **AI-reviewed research dataset step** on 19 September 2026.

## Result

- The current complaint training file is [`exports/complaint_training_v9_step1_research_candidate/manifest.json`](exports/complaint_training_v9_step1_research_candidate/manifest.json). It has **4,538 train records**: 3,881 complaint triage, 52 workflow, and 605 section-conditioned checks. Development remains **60**. No sealed cases are in the training file.
- Every **297** currently in-force BNS/IT offence section has at least **two** positive training complaints. **248** sections have exactly two. The exact audit is [`review_automation/positive_step1_final_v1/per_section.csv`](review_automation/positive_step1_final_v1/per_section.csv).
- We audited all **2,884** original positive rows (3,008 section labels because some rows have multiple labels), checked that each label points to a currently classified in-force offence and that available text hashes match, and recorded each label's disposition in [`positive_ledger.csv`](review_automation/positive_step1_final_v1/positive_ledger.csv). This mechanical check does not prove that every complaint satisfies every legal element.
- We replaced **28** legal-question or vague source rows that had supplied the second positive for a section. We added **15** different fact patterns where the two existing examples were close paraphrases. The new cases and labels are in [`step1_positive_revisions_v1.psv`](data_drafts/step1_positive_revisions_v1.psv).
- The earlier **266** weak or superseded candidate rows remain excluded, as documented by the existing training-readiness audit. The v8 bundle remains frozen. The complaint v9 manifest and review ledger are hash-pinned in the master SQLite database.
- The experimental mixed file was rebuilt as [`exports/mixed-source-v20-step1-nyaya-experiment/manifest.json`](exports/mixed-source-v20-step1-nyaya-experiment/manifest.json): **8,107 train** and **60 development** records. It combines complaint v9 with the unchanged **3,569 auxiliary Q&A** rows from v19. The master database's current research export points to v20 and keeps **55 separate sealed** records outside the trainer file.

## Checks

- All **297** eligible sections retain at least two positives; no remaining two-case pair has character similarity above **0.70**. This is a lexical screen, not proof of different real-world scenarios.
- No positive training text exactly duplicates a positive development text.
- The four trainer files match their SHA-256 manifest hashes; the SQLite database passes integrity and foreign-key checks. `verify_research_master.py` reproduced all **8,107 train**, **60 development**, and **55 separate sealed** rows from the current export. `validate_kb.py` passed the law-index and recommendation-gate checks.

## Limits

This closes the **review and repair of the existing positive examples**. It does not certify legal correctness or complaint accuracy. **263** short, source-grounded supplementary positives remain in training, and many rare sections still have only two synthetic positives. Those examples are useful for an initial research run but may not generalise to natural language. The next independent development and sealed cases must measure that before a reliability claim or a wider app release. The app's recommendation gate remains **19** sections.

Reproduce the bundle with `python phase1/scripts/complete_positive_step1.py` from the workspace root in a clean output directory. `publish_positive_step1.py` creates the mixed v20 export and pins the artifacts; `sync_research_export_to_master.py --export phase1/exports/mixed-source-v20-step1-nyaya-experiment` imports its rows into the master database. These scripts refuse to overwrite their versioned outputs.
