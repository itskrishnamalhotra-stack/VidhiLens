# Bulk training export, 18 September 2026

The earlier **3,049** figure counts only the source-checked, 19-provision complaint/workflow pilot. The **17,573** figure counts downloaded rows indexed for inspection; it was never a count of approved training examples. The previous `run_review_automation.py` checked hashes, classified sources and produced review queues. It did not promote rows or increase the training export.

`scripts/build_mixed_training_export.py` now uses a suitable downloaded dataset directly. It verifies pinned source hashes and the original pilot export, checks exact normalized question overlap against local training and held-out records and the publisher's validation/test splits, then writes `exports/mixed-source-v1/train_sft.jsonl` with a matching row-by-row provenance map.

| Export component | Train rows | What it teaches |
| --- | ---: | --- |
| Existing local pilot | 3,049 | Complaint triage and conversation workflow for 19 recommendable BNS/IT provisions; this includes silver variants |
| Nyaya-Train-v3, deduplicated | 5,268 | Grounded legal question answering with supplied statutory context; 1,303 records have BNS/IT as their source act and 3,965 cover other laws or abstention |
| **Mixed total** | **8,317** | Two tasks with different system instructions, in one trainer-format JSONL |

Validation is 35 local pilot records plus 280 Nyaya v3 validation records, or **315** total. The publisher's 857 test rows remain outside this export. Twenty-four Nyaya train questions repeated local train examples and were omitted. All 1,293 Nyaya v7 train questions repeat v3 train questions, so v7 would only inflate the count. The broader external records are preserved for provenance and possible general legal QA experiments, not evidence of BNS/IT complaint coverage.

The [Nyaya-Train-v3 dataset card](https://huggingface.co/datasets/NyayaLabs98/nyaya-train-v3) declares Apache-2.0 and says its synthetic answers passed the publisher's context-citation gate. It also reports that a LoRA trained on the data did not reliably beat its base model on their evaluation. Our export retains the publisher's original context and answers, but **we have not independently verified each legal answer**. The mixed file is trainer-format data, not proof that a complaint assistant trained on it will be reliable. Its map labels source, task, licence, source act and review status so training and evaluation can select the right rows. The original scoped pilot export remains the higher-assurance complaint-task subset.

The other indexed sources were not silently promoted. For example, the 2,219-row statutory triage set has section-label problems observed during the source audit; 2,148 BNS legal QA rows have not passed independent answer checks; 2,983 complaint/cyber rows lack a clear reusable licence; and the remaining records include statute references, synthetic topics, duplicate questions and held-out evaluations. Source popularity and a JSONL format do not verify legal labels. The next data task is bulk error detection and correction on the most relevant of those sources, followed by task-specific evaluation, rather than counting every indexed row as valid training.

Regenerate the mixed export with `python -X utf8 phase1/scripts/build_mixed_training_export.py`. Its `manifest.json` records counts, limitations and file hashes.
