# Term paper evidence plan

Owner: Krishna Malhotra. Fill result fields only after the corresponding run or review. This is an outline, not a completed paper.

## Suggested paper order

1. **Problem and boundary:** help a person describe an incident, see possible reviewed BNS/IT Act sections, answer missing-fact questions, and prepare a user-confirmed local draft. Explain that the prototype does not file an official complaint.
2. **Law sources and scope:** cite pinned India Code BNS/IT Act PDFs and amendment/commencement sources. Report 358 BNS and 125 IT Act indexed entries, 19 current first-release recommendation sections, and why other entries are held or unreviewed.
3. **Dataset construction:** describe fictional and licensed candidates, provenance, privacy screening, corrected/rejected rows, AI labels, review tier, group split, and number actually accepted. State plainly that there was no human or independent legal review, and do not call the sealed set legal gold.
4. **System architecture:** Firebase frontend/Auth/private session history; portable backend; reviewed-law retrieval; model candidate ranking and guided actions; database validation and explicit confirmation. Diagram the cloud/university deployment and the limited Colab demo role.
5. **Methods and ablations:** lexical retrieval baseline; optionally untuned embeddings; base model; supervised QLoRA adapter trained in Colab; retrieval plus adapter. Include model ID/revision, data hash, exact prompts/configuration, seed, train time, GPU type and approximate cost.
6. **Evaluation:** sealed unseen complaint set, per-section and abstention results, citation validity, edit/confirm/cancel tests, multi-user session isolation, latency/queue under load, and privacy checks. Report denominators and uncertainty. Keep pilot and final results separate.
7. **Errors and limitations:** show a few genuine mistakes with likely cause and fix. Explain AI-only reference-label limitations, scope gaps, law changes, language gaps, and that no official filing integration exists.
8. **Conclusion and next steps:** state only measured improvements and the cost/quality trade-off observed.

## Evidence folder to populate during Phases 2–4

| Evidence | Source of truth | When |
| --- | --- | --- |
| Legal source URLs, retrieval dates and hashes | `sources_manifest.json`, `priority_source_audit.json` | Already prepared; recheck near submission |
| Dataset counts, sources, rejection reasons and split hash | `data_readiness_report.json`, AI-reviewed scenario export and audit report | After Codex AI review |
| Baseline and adapter predictions per scenario | Versioned JSONL run outputs | Each experiment |
| Metrics and confusion tables | Script computed from saved predictions, not manually typed | After pilot/final test |
| Training checkpoint/resume proof | Colab run manifest and Drive checkpoint hashes | Phase 3 |
| Concurrent-user and access-control evidence | Load test logs with fictional IDs, Firebase Rules emulator results | Phase 4 |
| Screenshots of chat, source citation, question options, draft/edit/confirm | Demo build with fictional incidents | Phase 4 |
| Cost and latency | Colab usage record and deployment bill/host metrics | Phase 3–4 |

Do not put raw complaint narratives, tokens, or other personal details in screenshots or public appendix. If a numeric result has not been measured, leave it blank and say so in the paper.
