# Step 2: missing facts and difficult cases

Owner: Krishna Malhotra. Completed as an AI-reviewed research-dataset step on 19 September 2026.

## Current result

The current complaint trainer file is
[`exports/complaint_training_v10_step2_research_candidate/manifest.json`](exports/complaint_training_v10_step2_research_candidate/manifest.json).
It contains **4,538** train records and **60** development records:

- 3,881 complaint-triage records;
- 52 complaint-workflow records; and
- 605 candidate-section checks.

Every one of the **297** currently classified in-force BNS/IT Act offence
sections has all three Step 2 learning cases:

1. A normal triage complaint with material facts missing, labelled
   `insufficient_information`.
2. A candidate-section check labelled `uncertain` when an essential fact is
   not known.
3. A candidate-section check labelled `unsupported` when an essential fact is
   explicitly absent or contradicted.

The 605 candidate checks contain 297 `uncertain` checks, 308 `unsupported`
checks, and 11 of the unsupported checks point to another possible section.
The latter teaches the model that a failed candidate section is not a global
conclusion that no offence may apply.

## Quality repair completed

The prior Step 2 batch used repeated training cues such as “I need to know
that detail before assessing this section.” These give a model an easy shortcut
instead of teaching it to recognise missing facts.

The v10 revision removed those cues from **781** records:

- 225 generic “report is incomplete” endings removed;
- 278 candidate uncertainty cues removed and reasons made specific to the
  unresolved fact;
- 277 candidate unsupported cues removed;
- 1 section-number hint removed; and
- 18 missing-fact triage cases rewritten as natural incident reports.

The exact edits are in
[`edit_ledger.csv`](review_automation/part2_quality_final_v1/edit_ledger.csv).
The manual natural-language revisions are in
[`step2_missing_fact_revisions_v1.psv`](data_drafts/step2_missing_fact_revisions_v1.psv).

## Current master dataset

The optional mixed research export is now
[`exports/mixed-source-v21-step2-nyaya-experiment/manifest.json`](exports/mixed-source-v21-step2-nyaya-experiment/manifest.json):
**8,107** train and **60** development rows. It contains the v10 complaint
bundle plus 3,569 separately tagged auxiliary legal Q&A rows. It is an
experiment to compare during Colab training, not a replacement for the
complaint-only baseline.

The master SQLite database points to v10 for complaint training and v21 for
the mixed experiment. It keeps **55** sealed cases outside both trainer files.

## Verification

- Every current bundle file matches its SHA-256 manifest.
- The master SQLite file passes integrity and foreign-key checks.
- The master database reproduces all 8,107 training and 60 development rows
  in v21, with the 55 sealed rows still separate.
- The legal index and 19-section recommendation gate passed their verification.
- The revised Part 2 triage complaints contain no direct BNS/IT section number
  hints and no exact positive training/development duplicate was found.

## Boundary

This finishes the dataset construction and quality pass for missing facts and
candidate-section boundaries. The examples are AI-authored, source-grounded
research data. They need the independent development and sealed-test work in
Step 3 before we judge model accuracy or widen the 19-section app gate.
