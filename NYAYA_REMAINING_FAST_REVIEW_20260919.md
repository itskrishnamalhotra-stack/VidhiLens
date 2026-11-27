# Fast review of remaining Nyaya v3 rows — 19 September 2026

## Result

The previous v18 experiment used **987 of 5,539** Nyaya rows. This pass added
**1,160** more publisher train rows after screening BNSS and BSA legal Q&A
against official Ministry of Home Affairs Gazette PDFs:

| Source Act | Newly added |
|---|---:|
| BNSS 2023 (criminal procedure) | 803 |
| BSA 2023 (evidence) | 357 |
| **Total added this pass** | **1,160** |

The new Colab trainer-format experiment is
`exports/mixed-source-v19-nyaya-bnss-bsa-experiment/`: **8,092 train, 60
development**. Of the training rows, **2,147 are Nyaya Q&A**. The 280 Nyaya
publisher development rows remain separate from training, along with publisher
test. Thus **3,392 of the original 5,539** are still out of training: 3,112
publisher train rows plus 280 publisher development rows.

## Bulk checks

The reproducible builder is `scripts/build_nyaya_bnss_bsa_experiment.py`.
For every BNSS/BSA candidate it checked the primary Act and section, answer
citations against supplied passages, cross-Act references, and prompt length.
It compared the start of each retained statutory passage with the official
Gazette text, then kept only the passages needed by the question and answer.
Two overconfident BNSS answers found in the spot check were removed. The screen
held **95** BNSS/BSA train rows because their publisher passages did not match
the official PDF closely enough; one example paired BNSS Section 58 with the
text of Section 59. This is why source popularity or a small random sample
cannot approve the whole publisher file.

The 3,112 held publisher train rows are:

| Group | Held | Decision |
|---|---:|---|
| Constitution | 863 | Outside BNS/IT complaint scope; sample also uses “Section” for constitutional Articles. |
| Other unrelated Acts (Negotiable Instruments, Consumer Protection, Wages, marriage, domestic violence, RTI) | 1,173 | Outside the current product's law scope; no current official-text screen for these Acts. |
| Source Act unspecified, safety/general advice | 460 | Sample includes useful abstentions but also unsupported legal suggestions and advice that conflicts with the product's drafting flow. No bulk approval rule passed. |
| BNS/IT | 307 | Held by the earlier v18 citation, legal-text, cross-Act and sampled-answer screen. |
| BNSS/BSA | 309 | Failed this pass's citation, source-text, single-Act, answer or length checks. |
| **Total held publisher train** | **3,112** | |

The exact per-row decisions are in
`review_automation/nyaya_v3_screened_experiment/decisions.jsonl` (BNS/IT) and
`review_automation/nyaya_v3_remaining_fast_screen/decisions.jsonl` (remaining
publisher train). The initial 80-row stratified sample is in
`review_automation/nyaya_v3_sample_20260919/`.

## Training use and checks

The [v19 training file](exports/mixed-source-v19-nyaya-bnss-bsa-experiment/train_sft.jsonl)
is ready as an **experimental Colab input**. The [sidecar](exports/mixed-source-v19-nyaya-bnss-bsa-experiment/train_sft_map.jsonl)
marks which rows teach complaint triage, workflow, BNS/IT explanations, BNSS
procedure or BSA evidence. BNSS/BSA rows are auxiliary legal Q&A. They do not
add complaint-to-BNS/IT labels. Compare a model trained on v19 with the
complaint-only, v17 and v18 variants on the same independent complaint cases
before selecting a final model.

Checks passed: all four trainer-file hashes match the v19 manifest; the 8,092
train rows align with their sidecars; all 2,147 Nyaya source IDs are unique;
no publisher development row was added; and no added Nyaya question exactly
matches the 60 development prompts. The newly added prompts have a median
length of 1,705 characters (maximum 11,317).

Official texts used for the BNSS/BSA screen:
[MHA BNSS Gazette PDF](https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf)
and [MHA BSA Gazette PDF](https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf).
These are Act texts as published; this screen does not certify each legal answer
or later judicial interpretation.
