# Prebuild handoff: what is ready and what still needs work

Updated 17 September 2026. Owner: Krishna Malhotra. All model training will use Google Colab.

## Prepared now

- The pinned central BNS and IT Act source snapshots, hashes, amendment and commencement sources, a complete 483-entry section index, 67 source-checked texts, and a 400-entry queue for section text/kind review (89 also need status review).
- A first release allowlist of 19 source-checked complaint provisions; IT Act 66E held for a wording conflict; 66A, 72A and BNS 106(2) restricted by documented status.
- The other indexed provisions are not approved for first-release recommendations. Expanding beyond the 19-section scope requires another source/status/label review batch.
- A relational data model for incidents, structured facts, multiple legal labels, review status, group split, and guided/draft/edit/cancel conversations.
- A train/dev export command that refuses audit-failing or incomplete final data and keeps the sealed test local. No Colab training export exists yet because the final 300-case target is unfinished.
- A labeling guide, dataset contract, 161-item original screening queue (57 fictional project drafts and 104 public candidates), candidate dataset licence/provenance manifest, readiness report and dataset audit command. One original IT Act 66E draft is held; the 104 public examples remain quarantined after publisher-label errors were found. The expanded, reviewed fictional set has **250 accepted cases** (193 train, 24 dev, 33 sealed test) and four rejected superseded rows. The pilot split passes the current mechanical audit.
- A low-cost modeling direction for later evaluation: an existing open-weight model with possible QLoRA in Colab. The exact checkpoint and training recipe are deferred until the data and evaluation set are ready.
- A product boundary: the app may save a user-confirmed local complaint draft. It does not file with police or an official portal. The [official cybercrime portal](https://www.cybercrime.gov.in/Webform/FAQ.aspx) is a separate government service; [its guidance](https://cybercrime.gov.in/Webform/Accept.aspx) directs non-cyber or emergency matters to local police and lists 112 and 1930. Any future direct filing integration needs its own authorization, service agreement and testing.
- A portable deployment contract in `DEPLOYMENT_ARCHITECTURE.md`: Firebase web frontend; Firebase Authentication and private session history; same backend API on a cloud/university host; Colab training separate from a supervised emergency Colab demo. Multiple chats per user and simultaneous users are required.

## Remaining work other than model training and app coding

1. **Capture the course rubric when available.** The deadline is as soon as possible. Check required model comparisons, paper format, presentation/demo rules, and whether any extra training experiment is compulsory. Do not hold up the baseline app for this.
2. **Use the portable demo design.** No computer specifications are needed to start. Obtain university hardware details only when tuning model quantization and worker count for that host. Use a short-lived cloud host for a reliable final demo if the university server is not ready; Colab is for training and a supervised emergency interactive demo, subject to its terms and runtime limits.
3. **Codex expands the AI-labeled reference set beyond the completed 100-case pilot.** For every story, compare facts and possible/unsupported/uncertain labels with official source text, check privacy/licence/provenance, and record a reason and date. No human review is planned. AI-generated drafts remain pending until this separate source-grounded pass; accepted cases receive the `ai_reviewed` tier. Reach 300 distinct AI-reviewed incidents including 80 sealed-test and at least 60 abstention/out-of-scope incidents. Expand toward 500 only if useful. Report that final accuracy is against AI-created references, not lawyer-verified truth.
4. **Keep IT Act 66E held unless the source conflict is resolved.** An authoritative correction or qualified legal interpretation is needed to settle the “public/pubic area” conflict before that section enters the allowlist. If it stays held, the app must abstain or use other defensible provisions rather than silently suggest 66E.
5. **Check the legal release again near submission.** Review later central amendments/commencement and any state-specific claims the demo makes. For a real-world service, obtain qualified legal review of provision text, labels and filing guidance.
6. **Freeze the evaluation set and plan.** Group variants before split, review all test labels, check duplicates and leakage, pin hashes, and keep test answers away from prompt/threshold/model selection. The 100-incident pilot and final 80-case sealed target are specified in `EVALUATION_PLAN.md`.
7. **Prepare the final research evidence.** Follow `PAPER_EVIDENCE_PLAN.md`: record run manifests, actual Colab GPU-hours/cost, baseline and trained predictions, failure examples, screenshots, citations and limitations. Numerical results cannot be written honestly until models and app are tested.
8. **Implement privacy and retention choices.** For the academic demo, use fictional complaints; if real user reports are ever collected, document consent, retention, deletion and access controls before collecting them. Do not put raw complaints in analytics or a public repo. Test two-user isolation and several chats per account.

## Practical order

1. **Finish the law and data foundation first:** continue from 250 accepted fictional incidents, 49 structured fact states and 32 reviewed dialogue actions; source-review the 400 remaining law entries and create richer IT Act, abstention and draft/edit/cancel cases with structured facts. Reuse public wording only after individual repair and review. Keep 66E held.
2. **Freeze the evaluation data before development/training:** group incident variants, check duplicates and source permissions, and grow the pilot split to the 300-incident target with 80 unseen sealed-test cases. Keep the current 33 sealed cases out of any training or prompt selection.
3. **Then develop the product:** Python FastAPI retrieval backend, Firebase frontend, Auth, private multi-chat history, source-backed section search, guided questions and local draft/edit/cancel/confirm flow. Test two-account isolation early.
4. **Then train in Colab:** smoke test and checkpoint/resume first; compare the untuned baseline with a small QLoRA run on accepted train data. Keep the sealed test out of prompts and training.
5. **Connect and deploy:** add the chosen model worker, queue concurrent requests, load-test five users and multiple chats, then run the same API package on a short-lived cloud host or university server. Keep Colab as a supervised fallback demonstration.
6. **Finish the research product:** recheck official law status, freeze prediction files and measured metrics, record cost/latency/errors, capture fictional-case screenshots, and write the term paper with the AI-only review limitation.

The preparation is designed to avoid paying for Colab before the reviewed data and baseline show a reason to train. Google says [Colab's free GPU availability and limits vary](https://research.google.com/colaboratory/faq.html), so the budget cannot be promised in advance.
