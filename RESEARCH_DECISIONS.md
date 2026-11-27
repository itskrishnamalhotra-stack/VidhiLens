# Research decisions and source audit — 16 September 2026

Owner: Krishna Malhotra. Scope: a low-cost academic complaint assistant covering central BNS 2023 and IT Act 2000 text. These decisions are planning evidence, not professional legal advice.

## Statutory sources

- Keep the pinned [India Code BNS PDF](https://www.indiacode.nic.in/indiacode/bitstream/123456789/20062/1/a202345.pdf), [India Code IT Act PDF](https://www.indiacode.nic.in/indiacode/bitstream/123456789/1999/1/A2000-21%20%281%29.pdf), [MHA BNS commencement notice](https://www.mha.gov.in/sites/default/files/BhartiyaNyayaSanhita_24022024.pdf), and [MeitY Jan Vishwas memorandum](https://www.meity.gov.in/static/uploads/2024/03/MeitY-JVA-1.pdf). Local hashes and retrieval dates are in `sources_manifest.json`.
- The previous IT Act PDF is stale for sections 66A and 72A. The MeitY memorandum states the IT amendments began on 30 November 2023. Keep 66A and 72A out of criminal complaint suggestions.
- IT Act 66E remains held. The current India Code consolidation prints “public area” in Explanation (c), while another official reproduction prints “pubic area.” This affects a definition; resolve it against an authoritative enactment or correction before allowing suggestions.
- The recommendation set is a small audited central-law subset. State amendments, later notifications, judicial interpretation, and case-specific legal advice require a separate review before any live public service.

## Online dataset decision

| Candidate | Finding | Use |
| --- | --- | --- |
| [GSMS-B BNS sections](https://huggingface.co/datasets/GSMS-B/indian-legal-sections-bns-bnss-bsa-2023) | Apache-2.0; 358 BNS rows. Publisher says it was parsed from PDFs and warns of formatting artifacts. | Extraction comparison only. Official India Code remains the law source. |
| [GSMS-B BNS QA](https://huggingface.co/datasets/GSMS-B/Indian-Legal-QA-BNS-BNSS-BSA) | 2,148 BNS QA rows, six per section; templated questions rather than ordinary complaints. | Optional language examples after individual review. |
| [BNS statutory triage](https://huggingface.co/datasets/legalnlpresearcher/legal-statutory-triage-sft) | Locally audited 2,219 rows covering 287 BNS base sections. The publisher describes synthetic citizen queries. No IT Act coverage. Our 104-row in-scope screen found clear publisher-label mismatches. | Reject publisher labels for direct training. Candidate wording or hard negatives only after individual rewrite and source-grounded review; see `EXTERNAL_TRIAGE_QUALITY.md`. |
| [Nyaya train/eval](https://huggingface.co/datasets/NyayaLabs98/nyaya-train-v7-raft) | Local train file: 1,293 rows, of which 253 primarily BNS and 72 primarily IT Act; zero `verified: true` metadata rows. Separate evaluation set has a known BNS 75 penalty error. | Quarantine; do not treat as gold or sealed test. |
| [Complaint_and_Sections](https://huggingface.co/datasets/ri2000/Complaint_and_Sections) | Publisher claims 47,329 complaints with IPC labels. Access requires approval and terms; labels predate BNS. | Do not rely on access or auto-convert IPC labels. Privacy and mapping review would be needed. |
| [NariRaksha-1K](https://huggingface.co/datasets/vikhram-labs/NariRaksha-1K) | Card shows synthetic templates with legal-context errors (for example it calls BNS 316 “cheating”). Its displayed confidence is not a validated probability. | Exclude from legal labels and training import. |

No openly accessible dataset found in this search is already a reviewed set of ordinary complaints mapped to the current **BNS and IT Act** scope plus the app's follow-up/draft/edit/cancel actions. The project must create that set. The six downloaded candidate files remain hash-pinned and quarantined in `external_candidates_manifest.json`; the additional NariRaksha candidate was rejected from import based on its card. A wider survey and specific repair/reject rules are recorded in `DATASET_CATALOG.md`. All 104 unique usable in-scope BNS triage rows from the downloaded file are now in the 161-row candidate review queue, with their publisher labels still unverified.

## Model and compute decision

- Research model candidates: [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B-GGUF) for the conversational baseline and a compatible 4B checkpoint for Colab QLoRA, Apache-2.0. The earlier [Qwen3-4B-Base](https://huggingface.co/Qwen/Qwen3-4B-Base) is retained as an experimental comparison, not assumed to be the best chat starting point. Start with a retrieval-only app baseline; train only if the AI-reviewed data and tests support it. Pin exact revisions when experiments begin.
- Optional semantic retriever: [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B), Apache-2.0. Benchmark it against cheap lexical retrieval before paying for retriever training.
- [Google Colab's FAQ](https://research.google.com/colaboratory/faq.html) says free GPU access, hardware types and usage limits vary. Do not promise a specific free GPU, uninterrupted run or fixed price. Save complete hashed checkpoints to Drive and test resume before a long run.
- DAPT and retriever fine-tuning are measured experiments, not prerequisites. Use them only if validation shows a gain that justifies compute and review time.

## What the research cannot settle alone

The deadline is as soon as possible. The course rubric, acceptable review standard and whether extra experiments are compulsory remain project-specific. No final-demo computer specification is needed to start: the frontend will use Firebase, the backend package will be portable, and university-host hardware details matter only when tuning that deployment. A web search cannot certify future legal status or make unreviewed complaint labels trustworthy.
