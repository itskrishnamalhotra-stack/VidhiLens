# Fast data pipeline and trainability contract

Owner: Krishna Malhotra. Updated 17 September 2026.

## Current truth

- `db/master_dataset.sqlite` is the reviewed source of truth, **not** a file to hand directly to a LoRA trainer. It holds law, cases, labels, facts, action turns, splits and source records.
- `scripts/export_colab_data.py` is gated by law, label, privacy and split checks. When the gates pass, it writes train/dev structured JSONL and conversational `train_sft.jsonl` / `dev_sft.jsonl`, with hashes and sidecar maps. It does not export sealed test cases.
- `scripts/compile_sft_data.py --check-only` currently proves that the accepted train/dev rows can be converted to the conversational format without writing a training file. This is a format check, not proof of legal or model quality.
- The model-specific tokenizer and chat template are applied in Colab at training time. No manual copy/paste or relabelling should be needed between final database approval and the export.

## Faster assembly line

1. **Law ingest:** Keep one pinned official India Code snapshot per act plus amendment/commencement sources. Parse all sections and record page, hash and raw text automatically. No scraped publisher label becomes law truth.
2. **Law preflight:** Run two extraction methods and compare section boundaries, titles and normalized text. Automatically group exact agreements, formatting differences and substantive differences. Generate review packets of 50–100 provisions with the official page and diff. AI review resolves every substantive difference, amendment, omission and commencement exception. Store signed-off text, status, kind and rationale in one ledger; fail closed on unresolved rows.
3. **Case preflight:** Index all licensed candidates, strip duplicates and near duplicates, detect language and possible personal data, classify whether a row is a complaint, legal QA, general dialogue or external evaluation, and retrieve candidate sections. Quarantine source answers by default.
4. **Case production:** For each eligible offence, build a legal-element checklist once. Generate batches of 100–200 distinct incident families with positive, missing-element, wrong-section, multi-section and out-of-scope examples. Keep direct evidence spans and a question for missing facts. AI review checks the proposed label against the official text and accepts, corrects or holds each row.
5. **Feedback loop:** Audit split leakage, near duplicates, label legality, language mix, coverage and train-only workflow actions after each batch. Spend the next batch on the largest coverage or error gap. Never fill counts by cloning one story across splits.
6. **Training export:** Compile only approved train/dev records into conversational SFT JSONL. Parse every exported row, verify target schema and source hash, record a manifest, and keep sealed cases local. A small Colab loading test proves the files can enter the chosen trainer before any expensive training run.

Automation should handle most copying, parsing, deduplication, linking, diffing, packaging and reporting. It cannot certify a legal status or a generated complaint merely because two strings match. The AI reviewer remains responsible for legal judgement and for correcting flagged cases. The aim is to automate roughly 80–90% of repetitive handling, **not** to auto-approve 80–90% of legal conclusions.

The first law preflight is implemented as `scripts/preflight_law_review.py`. It uses a second PDF parser on the pinned official snapshots and writes four 100-row packets to `data_drafts/law_preflight_packets/`. In the initial run, 383 of 400 entries passed a five-token sequence agreement threshold, 17 showed parser differences, and 145 of the agreeing entries still had editorial cleanup flags. No row was legally approved by this check.

The combined read-only preflight is `scripts/run_review_automation.py`. Its 18 September 2026 run accounted for all 17,573 indexed public candidates and wrote `review_automation/SUMMARY.md`, a row-level disposition CSV, 28 case review candidates with official section context, and 385 current law review tasks in 50-row packets. It checks source hashes and database integrity but approves no new legal text or training examples. Use the output to resolve flagged gaps before another training export.

## Completion rule

The dataset is not called complete until all intended law provisions have source-checked status/text, train/dev/held-out examples cover the intended complaint and workflow behaviours, the export produces trainer-compatible files, and every export gate passes. A later model evaluation still determines whether more examples are required.
