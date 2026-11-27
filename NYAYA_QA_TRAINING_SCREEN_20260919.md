# Nyaya v3 Q&A training decision — 19 September 2026

The 5,539 Nyaya v3 rows are legal question and answer examples. Their questions
contain supplied statutory passages. They do not label ordinary complaints
with applicable BNS/IT Act sections.

## Check and decision

- The existing whole-file screen found 5,539 structurally usable chat rows:
  5,259 publisher train and 280 publisher development. Of these, 4,168 were
  outside BNS/IT scope, including publisher development rows.
- A reproducible 80-row stratified sample is in
  `review_automation/nyaya_v3_sample_20260919/`. We inspected answers across
  BNS, IT Act, BNSS/BSA, other Acts, English, Hindi, Hinglish, and abstention.
- The full set did **not** pass the intended check. An IT Act Section 45 answer
  and its supplied passage use an obsolete ₹25,000 limit; the current official
  consolidation has different limits. A sampled BNS Section 68 answer treated
  a manager's unwelcome advances as though the offence's intercourse element
  were already established. Other sampled rows answered topics outside the
  app's BNS/IT complaint task or conflicted with its complaint-drafting flow.
- We built a separate, trainer-format experiment that adds **987** screened
  publisher train rows: **831 BNS** and **156 IT Act**. The base 5,945 train
  records remain intact, making **6,932 train and 60 development** records in
  `exports/mixed-source-v18-nyaya-screened-experiment/`. The 280 Nyaya
  publisher development rows and all publisher test rows remain out of training.

## What the screen did

`scripts/build_nyaya_screened_experiment.py` checked citations, target Act,
current legal status, and the supplied section text against the verified
statute database. It excluded rows with other Acts in the answer, missing
primary references, unsupported citations, or changed legal text. Two
answer errors found during sample inspection were also excluded. It then
replaced each accepted row's long publisher passage with the relevant verified
BNS/IT provisions and a neutral system instruction. The median accepted
question prompt is 1,481 characters. The original Nyaya prompts had a median
length of roughly 10,958 characters, so this also cuts Colab sequence cost.

Of the 5,259 publisher train rows, **4,272 were held**, including 3,965 outside
BNS/IT scope. The exact reason for every decision is in
`review_automation/nyaya_v3_screened_experiment/decisions.jsonl`.

This is a **sampled and mechanically screened auxiliary Q&A experiment**, not
individual legal certification or complaint supervision. Train the complaint
only bundle and v17 first, then compare v18 on the same untouched complaint
development and sealed-test cases. Keep v18 only if it improves the complaint
task without worsening wrong-section suggestions or abstention.

## Files and reproduction

- `exports/mixed-source-v18-nyaya-screened-experiment/train_sft.jsonl`: direct
  chat training input for a Colab LoRA experiment.
- `train_sft_map.jsonl`: source, task, review and provision sidecar, one row per
  training example.
- `dev_sft.jsonl` and `dev_sft_map.jsonl`: the unchanged 60-case development set.
- `manifest.json`: counts and SHA-256 hashes for the four trainer files.

Rebuild with `python phase1/scripts/sample_nyaya_v3_for_review.py` and
`python phase1/scripts/build_nyaya_screened_experiment.py` from the project
root. The builder rejects changed pinned input exports.

Final checks passed: 6,932 train rows align with sidecars and manifest hashes;
all 987 added source IDs are unique; no exact added-question overlap with the
60 development prompts; IT Act sections 44, 45 and 66A are absent from the
added rows. The existing v17 export remains available as the comparison run.

Official source check for the changed IT Act limit:
[India Code's current IT Act consolidation](https://upload.indiacode.nic.in/view-casepdf?id=AC_CEN_45_76_00001_200021_1517807324077&type=act).
