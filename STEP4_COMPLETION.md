# Step 4: mixed Q&A decision and Colab data freeze

Owner: Krishna Malhotra. Completed on 19 September 2026 as a research-data decision. Model selection remains a training and evaluation task.

## Decision

The first Colab run will use the complaint-only baseline. A second run can test whether screened BNS/IT legal Q&A improves complaint performance. Both files are directly trainer-format JSONL and use the same 326-case development set. Neither contains the 90-case sealed test.

| Frozen variant | Train rows | Contents | Role |
| --- | ---: | --- | --- |
| `complaint_only` | 4,538 | Reviewed research complaint triage, candidate checks and workflow | Primary baseline |
| `complaint_plus_bns_it_qa` | 5,525 | Same 4,538 plus 987 screened Nyaya BNS/IT grounded Q&A | Comparison run only |

Files are in [`exports/colab-step4-v1/`](exports/colab-step4-v1/) and the upload-ready archive is [`exports/colab-step4-v1.zip`](exports/colab-step4-v1.zip). The root manifest records every file hash and the parent research/evaluation manifests. The current sealed test remains [`exports/evaluation-step3-v6/sealed_test.jsonl`](exports/evaluation-step3-v6/sealed_test.jsonl) and is absent from the archive.

## Why the other mixed records are held

- The 987 selected Nyaya Q&A rows passed the earlier current-text, citation, source-act and sampled-answer screens. They are still auxiliary legal explanations, not ordinary complaint labels, and individual legal answers are not certified. Their extracted questions had no lexical similarity at or above 0.75 to the 326 development prompts.
- The additional 1,160 Nyaya BNSS/BSA Q&A rows concern criminal procedure and evidence, outside the first product's BNS/IT section-selection task. Keep them in the research archive for a separate later feature.
- The 1,422 GSMS BNS Q&A rows passed a mechanical source screen but remain semantically uncertified. They are retained in the research archive for an ablation only if the first two runs show a need for more auxiliary Q&A.
- The other 3,112 Nyaya publisher-train rows were held by the previous source, citation, legal-text, scope and answer screens. The 280 publisher-development rows remain held; no publisher evaluation row was promoted into the Colab training files.

This decision keeps training focused on complaint classification and uses the smallest useful comparison. It does not discard source material. The 8,107-row mixed research export remains pinned in the master database as a provenance and experiment archive, while the two smaller frozen variants are the first Colab inputs.

## Verification

- Source manifests and frozen file hashes match. Both train files align one-to-one with their provenance sidecars; all records parse as JSON.
- The 4,538 baseline train rows are byte-for-byte the approved Step 2 complaint training file.
- The 987 selected Nyaya source IDs are unique and marked as screened BNS/IT auxiliary Q&A.
- The ZIP archive passes its CRC check, reproduces all ten variant files and their hashes, and contains no sealed-test case.
- The master SQLite database passes integrity and foreign-key checks. The `current_colab_training_manifest` pointer identifies this freeze.

## Training decision rule

Run `complaint_only` first in Google Colab. Run `complaint_plus_bns_it_qa` using the same base model, evaluation prompts and budget. Choose the second adapter only if development performance on ordinary complaints improves without worsening wrong-section suggestions or abstention. Open the sealed test only after model and threshold choices are fixed, and report its results as agreement with AI-reviewed research labels rather than independent legal accuracy.
