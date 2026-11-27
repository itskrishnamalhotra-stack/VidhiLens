# Step 3: independent development and sealed evaluation cases

Owner: Krishna Malhotra. Dataset construction completed on 19 September 2026 as an AI-reviewed research evaluation set.

## Frozen current files

- Development and sealed cases: [`exports/evaluation-step3-v6/manifest.json`](exports/evaluation-step3-v6/manifest.json).
- Mixed trainer export with the expanded development split: [`exports/mixed-source-v27-step3-evaluation/manifest.json`](exports/mixed-source-v27-step3-evaluation/manifest.json).
- Master inventory: [`db/master_dataset.sqlite`](db/master_dataset.sqlite). The research export contains 8,107 training records, 326 development records, and 90 separate sealed-test records.

The 326 development records include 297 positive complaint cases covering all 297 currently classified in-force offence sections, 16 missing-information cases, 10 out-of-scope cases, and 3 workflow cases. The 90 sealed records include 69 positive cases covering 47 sections, 15 missing-information cases, 4 out-of-scope cases, and 2 workflow cases. The 19 first-release sections have sealed positive coverage. The sealed file is excluded from both trainer files.

## Correction made during construction

An automated screen initially selected 202 publisher-labelled public prompts. A fact-to-law inspection found frequent incorrect labels, so **none of those 202 prompts remain in the current development split**. They were replaced with statute-grounded, AI-authored incident descriptions. A further 43 replacements were rewritten because they were too similar to training text. Earlier exports remain versioned for traceability and should not be used as the current evaluation set.

## Checks completed

- All 297 development positive IDs point to currently classified in-force offence sections.
- Stored law-text hashes checked for 262 development records and 84 sealed records; zero mismatches. All other positive and uncertain IDs also passed section-status checks.
- Exact train/held-out matches: 0. Lexical train/held-out similarities at or above 0.75: 0 in [`research_leakage_step3_v6/summary.json`](review_automation/research_leakage_step3_v6/summary.json).
- Recorded incident-family identifiers appear in only one split; no cross-split identifier collision was found.
- The master database reproduces the current 8,107 train, 326 development, and 90 sealed records; legal database validation passes.

## Evaluation boundary

These are **AI-reviewed research labels, not lawyer-verified legal gold**. Many positive cases explicitly include statutory elements, so scores on this set may overstate performance on ordinary, incomplete complaints. Lexical and identifier screens do not prove semantic independence. Report measured model results only after saved predictions are evaluated, and never tune on the sealed cases. The 19-section live recommendation gate remains in place until a separate release assessment supports expansion.
