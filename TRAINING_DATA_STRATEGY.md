# Training data decision — use both sources, with review

Owner: Krishna Malhotra. Training runs only in Google Colab. This document is a checklist for reaching a usable training package; it does not claim the package is complete today.

## The three data layers

1. **Law reference database:** all BNS and IT Act section entries are indexed from saved official PDFs. This is the source the app retrieves from. Only manually checked `verified_text` with current status may be shown or recommended. The model does not need to memorize every section.
2. **AI-reviewed complaint examples:** create our own examples for the first approved sections. Each scenario stores its wording, facts and missing facts, possible/unsupported/uncertain section labels, reason, AI reviewer, privacy status, and train/dev/sealed-test split. This is the core material for retrieval evaluation and LoRA training. Report that the references are AI-labeled, not lawyer-validated.
3. **Reviewed conversation examples:** record when the assistant should ask a follow-up, present selectable options, explain uncertainty, offer a draft, apply a precise edit, confirm, or cancel. User confirmation and valid provision checks also remain enforced by the app.

## How online data helps

- Use the downloaded BNS section dataset to cross-check extraction, not as the official source.
- Screen the 2,148 BNS QA pairs for usable wording. The 2,219-row BNS triage file has clear publisher-label errors in the 104 queued in-scope rows; its labels are rejected for direct training. Individual wording examples may be rewritten or used as hard negatives only after source-grounded review. Keep original source ID/licence and correction notes.
- Screen the Nyaya chat examples for Hindi/Hinglish and grounded response patterns. Their `verified` field is false and their workflow differs from ours, so they need manual review before reuse.
- Keep the 500-row Nyaya evaluation set outside training. Its BNS 75 example already disagrees with the official punishment text.
- The gated 47,329-row complaint dataset uses older IPC labels. Do not make project progress depend on gaining access or automatically converting IPC numbers to BNS.

## Build our first reviewed set in order

1. Use the 19 source checked priority sections and three support provisions for the prototype. Keep IT Act 66E out until its conflicting official wording is resolved. Add other sections only when cases reveal a real gap.
2. Write a **pilot** of about 80–120 distinct fictional complaint scenarios covering clear matches, similar but unsupported cases, missing information, and out-of-scope matters. Review facts and labels before any model experiment.
3. Add follow-up and draft/edit/cancel conversations tied to those scenarios. Include wrong or uncertain user claims, changed answers, ambiguous edits, and cancellations.
4. Split by scenario group before paraphrasing; keep all variants of one incident in one split. Never use the sealed test for prompt selection or model tuning.
5. After the baseline and pilot error review, aim for 300 distinct reviewed scenarios including 80 sealed-test and at least 60 insufficient-information/out-of-scope incidents; expand toward 500 only if quality and time permit. This is a planning target, not a substitute for quality. Track per-section positives, near misses, abstentions, language, and action examples.
6. Export only accepted, privacy-reviewed, source-traceable examples. Pin database, dataset, model, code, and source hashes in the Colab run manifest.

## Current status

Run `python phase1/scripts/report_data_readiness.py` for exact counts and blockers. As of 17 September 2026, the law index contains 358 BNS and 125 IT Act entries. **Sixty-seven provisions have source-checked text; 19 priority sections pass the academic prototype recommendation gate, and 89 entries still need legal-status review; 311 commenced BNS sections still need text and kind review.** IT Act 66E is held over a conflict between official reproductions. There are **250 accepted AI-reviewed fictional scenarios (193 train, 24 dev, 33 sealed test), 49 structured fact rows, and 32 accepted conversation actions**. The pilot split passes mechanical audits, but the final 300-case, 80-sealed, 60-abstention target is unfinished. The public files remain quarantined; the BNS triage source has demonstrably unreliable publisher labels. The project is **not ready for final LoRA training** yet. A later pipeline smoke test in Colab must not be reported as legal performance.

## Decision on the model

Start with an existing open-weight model and a retrieval-based app baseline. If the reviewed training set and held-out evaluation show a clear gain, train a LoRA/QLoRA adapter in Colab. Do not train a foundation model from scratch. Do not pay for large-scale training merely because more unreviewed public rows are available.
