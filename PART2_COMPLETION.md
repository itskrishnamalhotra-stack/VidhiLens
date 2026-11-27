# Part 2: missing facts and difficult section boundaries

Owner: Krishna Malhotra. Status: **complete as an AI-authored research dataset step**, 19 September 2026.

> **Current version notice.** The v8/v17 paths and counts below are historical
> snapshots. Step 2's final quality pass created complaint v10 and mixed v21,
> removing repeated answer cues and adding natural-language rewrites. Use
> [`STEP2_COMPLETION.md`](STEP2_COMPLETION.md) and
> `exports/complaint_training_v10_step2_research_candidate/` for the current
> trainer candidate.

## What is ready

- All **297** currently classified in-force BNS/IT Act offence sections have at least one train-format complaint with a material fact left open. The model target is to ask for that fact rather than force a positive section.
- All **297** also have a section-conditioned `uncertain` check and an `unsupported` check. There are **594** such checks, plus **11** harder comparisons where one section fails but a different section may apply.
- The **19** currently approved recommendation sections have more detailed complaint-style pairs. The wider 278-section matrix has compact, section-specific cases. Three labels were corrected after spot review; source corrections are pinned separately.
- The current unified complaint-training candidate is [`exports/complaint_training_v8_research_candidate/manifest.json`](exports/complaint_training_v8_research_candidate/manifest.json). Its train split contains **3,866 triage**, **52 workflow**, and **605 candidate-check** records, **4,523** in total. The development split contains **57 triage** and **3 workflow** records. No sealed case is in this bundle.
- The current mixed research experiment is [`exports/mixed-source-v17-complaint-gsms-research/manifest.json`](exports/mixed-source-v17-complaint-gsms-research/manifest.json): **5,945 train**, **60 development**, and **55 additional sealed** records indexed in the master SQLite database. It combines the **4,523** complaint v8 train records with **1,422** screened GSMS BNS auxiliary Q&A rows. The 5,259 Nyaya train and 280 Nyaya development legal Q&A rows were mechanically screened and held from this experiment; they remain available in the versioned v15 research inventory and public-source index. The complaint-only v8 bundle remains an unchanged baseline.

## How the labels work

`triage` receives only a complaint and returns a possible section, a fact to ask about, or an out-of-scope outcome. `candidate_check` receives a complaint **and a named candidate section**. It answers `uncertain` if a necessary fact is unknown and `unsupported` if a necessary fact is contradicted. An `unsupported` answer for BNS 304, for example, must never be turned into a global claim that no offence is possible: the same facts might support BNS 303.

The [`train_sft_map.jsonl`](exports/complaint_training_v8_research_candidate/train_sft_map.jsonl) sidecar gives each row's task family and source. The master database pins the bundle and the Part 2 source files with hashes and compressed copies. The current training-bundle pointer is `current_complaint_training_bundle` in `master_dataset_info`.

## Checks run

- [`verify_part2_final.py`](scripts/verify_part2_final.py) checked every in-force offence's positive and missing-fact coverage, both candidate-check labels, task counts, section text hashes, bundle file hashes, master database copies, and database integrity. Its result is [`summary.json`](review_automation/part2_final_v1/summary.json).
- The research export's exact and lexical split screen found **zero** train-versus-development/sealed complaint matches at similarity **0.75** or higher; see [`research_leakage_v14`](review_automation/research_leakage_v14/). This does **not** establish semantic or scenario-family independence.
- The 594 section checks and 11 extra comparisons were screened for close lexical overlap with held-out complaints. Three sampled boundary statements were corrected in [`part2_corrections_v1.json`](data_drafts/part2_corrections_v1.json).

## What this does not prove

All new cases were authored and checked by AI against stored statutory text; no independent legal expert validated every label. The 278-section matrix uses repeated phrasing and concise facts. The model may memorize that phrasing or fail on natural complaints. The 19-section app recommendation gate has **not** expanded. Do not describe these records as a gold legal dataset or claim the model will be reliable before independent testing.

## Next dataset steps

1. **Part 3:** Write genuinely independent development and sealed-test complaints, including positives, missing facts, and confusing alternatives. This is the next task and will measure generalization beyond these synthetic patterns.
2. **Part 4:** Quality-screen the 5,259 separate train legal Q&A records and decide, based on evaluation, whether any should be mixed into complaint training.
3. Only after those dataset steps: train and test a LoRA adapter in Google Colab. Keep the sealed test outside training and tuning.
