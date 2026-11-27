# Evaluation plan to lock before training

Owner: Krishna Malhotra. All final scores come from saved predictions on previously unseen, reviewed scenarios. Do not fill numeric results until measured.

## Question the paper must answer

Can a reviewed-law retrieval pipeline plus a small Colab-trained open-weight adapter identify plausible BNS/IT Act provisions from ordinary complaints, ask for missing facts, and abstain when the first-release scope does not support a section? Does each added training stage improve held-out results enough to justify its cost?

## Data and split rules

- Split by `scenario_group`, not text row. Every paraphrase, translation, follow-up and edited version of one incident stays in one split.
- Development split selects prompts, thresholds, model checkpoints and retriever. The sealed test is opened once for final comparison.
- Krishna's target is 300 distinct reviewed incidents, with 80 sealed-test incidents and at least 60 insufficient-information or out-of-scope incidents across the complete set. Expand toward 500 only if review quality and time permit. This is a target, not a claim that those examples exist today. Report actual counts and class balance.
- The current Step 3 research evaluation export has 326 development and 90 sealed records, with the sealed file kept outside trainer exports. Its construction and limitations are recorded in `STEP3_COMPLETION.md`. Report scores as agreement with AI-reviewed reference labels, not independent legal accuracy.
- The sealed set includes clear matches, close legal near misses, missing facts, and out-of-scope cases across BNS and IT Act; each of the 19 enabled sections should have coverage where coherent cases can be written. Record any uncovered section instead of inventing easy duplicates.
- No public dataset is the sealed reference test. Use project scenarios labeled through a separate source-grounded Codex AI review, with review tier explicitly reported. Because the user has chosen no human review, this measures agreement with AI-created reference labels and catches engineering errors; it is **not** an independent legal-accuracy estimate. Do not call this set lawyer-verified or legal gold.
- Add explicit categories for theft/snatching, hurt/grievous hurt, cheating/personation, threat, sexual harassment/stalking/voyeurism, IT misuse/identity/impersonation, online content and out-of-scope.

## Comparisons

1. Lexical retrieval over the 19 eligible sections.
2. Untuned open embedding retrieval against the same sections if it runs within cost limits.
3. Base model only, SFT adapter only, and production retrieval plus the chosen adapter. Keep any DAPT or tuned retriever branch as an extra comparison only if actually run.
4. The guided complaint/draft workflow receives separate behavioral tests; do not infer its quality from section classification scores.

## Metrics with denominators

- Retrieval: Recall@1/3/5, MRR and, for multi-label cases, nDCG@5. Show counts of relevant provision IDs and number of queries.
- Section selection: exact-set accuracy, micro/macro precision and recall, top-k recall, invalid-ID rate and proportion of outputs with a valid source citation.
- Abstention: precision, recall, F1 and confusion table for `insufficient_information` and `out_of_scope` separately.
- Dialogue: percentage of missing-fact cases with a relevant follow-up; unnecessary-question rate; preservation of user facts; correct edit patch; cancel behavior; no save before explicit confirmation.
- Operations: JSON parse success, latency on the actual demo machine, memory use, load success, and Colab GPU-hours/cost. Record failed runs as well as successful runs.
- Multi-user operations: at least five simulated signed-in users, multiple sessions each, overlapping turns, restart recovery, p50/p95 response time, queue wait, timeouts, and cross-user access denials. Measure on cloud or university host, since Colab is only an interactive emergency demo path.
- Safety/error counts: stale or blocked ID suggestions, hallucinated legal text, unsupported certainty, invented facts, prompt-injection compliance and incorrect claim of official filing.

## Acceptance checks

- Every shown provision ID exists in the active `recommendable_provision` view and every displayed excerpt is retrieved from `verified_text`; target 100% on every tested output.
- No accepted test incident appears in train/dev or their paraphrase families; zero known cross-split duplicates after review.
- A complaint with too little information must be able to return no section. A matter outside the 19-section scope must be able to return no section and a plain explanation.
- Save/edit/cancel flow must retain original user words, show changes, reanalyse legally material edits and require final consent before local save.
- Firestore Rules and backend tests must deny user A access to user B's sessions, messages and drafts. A duplicate or stale confirmation must not save the wrong draft version.
- For every metric, store the underlying scenario-level predictions and version IDs; compute the metric from those files rather than typing a number into the paper.

## Error review

For each mistaken case, record: scenario ID, expected outcome/sections, predicted outcome/sections, retrieved candidates, missing or contradicted fact, failure stage (retrieval/model/validation/UI/data label), corrective action, and whether the test set was already opened. After opening the sealed test, any fix is a new version and requires a new untouched test set for an unbiased later estimate.
