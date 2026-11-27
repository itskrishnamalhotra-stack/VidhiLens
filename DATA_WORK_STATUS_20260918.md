# Data work status, 18 September 2026

## Why the released pilot has only 19 sections

The master database indexes 358 BNS and 125 IT Act sections. Nineteen were previously approved for the pilot's complaint suggestion and training export. The gate requires checked legal text and status, a useful offence classification, fact examples, and a recommendation release decision. Many other sections have source text but no checked complaint examples or release decision. Some entries are definitions, procedures, exceptions, omitted provisions, or mixed sections whose subsection matters. A source-index entry is not automatically a safe complaint label.

## Work completed in this pass

1. `scripts/audit_complaint_pool_v2.py` checked all 3,544 rows in three complaint-like sources. It wrote `review_automation/complaint_pool_v2/row_audit.csv` and `summary.json`. It held 2,128 rows with structural or prior-review flags and placed 1,416 in a semantic review queue. None of these 1,416 is approved merely by the automated screen. The screen fixed source-role confusion: legal questions and non-offence section labels are kept out of complaint training.
2. `scripts/review_priority_source_rows_v2.py` read all 78 source rows mechanically linked to seven of the newly targeted BNS sections. It held 69 whose reported facts did not justify the publisher's label or were too repetitive or unclear. It corrected nine targets against the official text, discarded the publisher answers, and wrote a decision ledger plus trainer-format rows.
3. `scripts/build_gap_examples_v2.py` authored 69 distinct trainer-format research records for nine additional, source-checked sections: BNS 109, 124, 140, 305, 308, 309 and 324; IT Act 67B and 70. They comprise 37 train, 12 development, and 20 sealed test records. The set includes missing-fact questions and draft, edit, confirm and cancel workflow examples. It does not multiply one story into many surface variants.
4. `scripts/verify_gap_work_v2.py` checked hashes, target schemas, exact split disjointness and similarity between the new sealed cases and new training cases. It wrote `coverage_gaps.csv` and `coverage_summary.json`. No exact cross-split duplicate or new sealed/train pair at text similarity >=0.75 was found. The new sealed records are kept in a separate local JSONL and are absent from the Colab pilot/mixed training export.

## Completion boundary

The new cases are research examples in `data_drafts/gap_examples_v2/`, not released app suggestions or final-model training targets. Nine new sections now have examples for evaluation; 271 rows currently marked as in-force offences still lack even one positive train example in the existing pilot and this expansion. This count also includes any misclassified offence rows, so each needs a status/kind/use decision. Of the 1,416 rows in the semantic-review queue, 78 were reviewed in this pass and **1,338 remain**. The full BNS/IT dataset is therefore **not complete**. Increasing row count without those decisions would train avoidable section errors.

The original mixed export remains 8,317 trainer-format records. A new **research candidate** export at `exports/mixed-source-v2-research/` adds 37 authored train records, nine corrected source train records and 12 development records, for **8,363 train and 327 development records**. The 20 new sealed test records are absent from that export. These examples are trainer-format and can be evaluated experimentally; they do not yet authorise the app to suggest the nine sections. Use the nine-section research set to evaluate expansion and correct any case or source issue found before app release. Keep the sealed test file out of all training and example-selection steps.

Official source PDFs in `sources/` are pinned from [India Code BNS](https://www.indiacode.nic.in/bitstream/123456789/20062/1/a202345.pdf) and [India Code IT Act](https://www.indiacode.nic.in/bitstream/123456789/13116/1/it_act_2000_updated.pdf); the master database records the section text and source page used for the new examples.

## Later update: source disposition and section-floor research

The earlier counts above are a historical snapshot. `scripts/close_noisy_source_queue.py` has now assigned a training disposition to all 3,544 intake rows in `review_automation/complaint_pool_v2/final_training_dispositions.csv`. The 1,338 formerly pending `statutory_triage` rows were **excluded at source level**, because a sample of the publisher's section labels contained clear fact-to-law mismatches. They were **not individually fact-to-law reviewed** and must not be counted as verified or accepted training cases. The disposition ledger records this distinction explicitly.

`scripts/correct_nonstandalone_kinds.py` corrected two wrongly offence-marked provisions: BNS 71 is a repeat-conviction sentencing rule and BNS 165 is a monetary penalty for a vessel master. `scripts/build_section_floor_examples.py` drafted one source-grounded, trainer-format positive case for each of the other 269 uncovered in-force offence sections. Each new record identifies its provision, source PDF page and legal-text hash. These are single AI-authored research cases; they do not establish reliable section prediction or approve those sections for live suggestions.

`scripts/build_mixed_training_export_v3.py` verified the existing export hashes, kept the 20 sealed cases separate, checked exact input overlap, and joined the research cases into `exports/mixed-source-v3-research/`. It contains **8,632 train records and 327 development records**. Of the 297 provisions now classified as in-force offences, 19 have pilot coverage, nine have the earlier research set, and 269 have the new single-case research coverage. The mixed count includes legal question-answer records with a different task from complaint classification. The new section examples need stronger, independent development and test cases, error analysis, and a current-law check before release or any claim of dependable coverage.

## Later update: all 1,338 held statutory-triage source prompts inspected

The source prompts were read against the relevant BNS provision text. `scripts/review_remaining_statutory_source.py` records a decision for each of the 1,338 in `review_automation/complaint_pool_v2/remaining_1338_review/decisions.csv`, with hashes linking back to the original source lines. Publisher answers were discarded.

- **212** prompts became source-grounded, positive, trainer-format research cases: 149 keep the same whole-provision number and 63 were relabelled.
- **54** became trainer-format examples that ask for a specific missing fact before proposing a section.
- **11** were near duplicates of selected cases and were held out of training.
- **1,061** remain unlabelled challenge prompts. Together with the 11 duplicates, the separate challenge file contains **1,072** rows. These include legal/defence questions, short accounts with missing elements, and mismatched source labels. They are useful for retrieval inspection and future error analysis, but they are neither supervised training records nor scored test records. Do not assign a positive or negative legal label to them without further case-specific evidence.

`scripts/sync_remaining_source_review.py` links the dispositions to the indexed source rows in the master database. The updated unified research export at `exports/mixed-source-v4-research/` has **8,898 train and 327 development records**; the 20 sealed cases remain separate. The added short examples are research candidates, not a claim of reliable model performance or live recommendation approval. The original statutory-triage source had many incorrect labels, so the relatively small promoted share is deliberate.
