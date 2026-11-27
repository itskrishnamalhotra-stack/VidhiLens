# BNS public triage candidate quality screen

16 September 2026. Reviewer: Codex AI. Source: `legalnlpresearcher/legal-statutory-triage-sft`, pinned file and hash in `external_candidates_manifest.json`. The 104 locally queued in-scope rows were inspected as candidate wording; this is a source-level rejection of their **publisher labels**, not a legal review or acceptance of all 104 rows.

## Directly observed label problems

| Queue row | Publisher label | Complaint says | Why the label is unsafe |
| --- | --- | --- | --- |
| `TRIAGE_00235` | BNS 304 | Someone tried to lock the user in a room | BNS 304 concerns snatching movable property, not confinement. |
| `TRIAGE_00421` | BNS 304 | Knife attack on a street | No taking or attempted snatching is stated. |
| `TRIAGE_00790` | BNS 304 | Someone grabbed the user's arm | Grabbing an arm is not grabbing movable property. |
| `TRIAGE_01136` | BNS 304 | A push after an accidental bump | No property taking is stated. |
| `TRIAGE_01626` | BNS 304 | Someone took a phone without permission | The story omits the sudden/quick/forcible seizure from a person or possession required for snatching; it may describe ordinary theft. |
| `TRIAGE_00091` | BNS 316 | Someone altered a bank cheque | The text does not state entrustment or dishonest conversion of entrusted property. |
| `TRIAGE_01875` | BNS 316 | Organized crime and unexplained wealth | No entrustment or conversion is stated. |
| `TRIAGE_01953` | BNS 351 | Social-media messages inciting violence against government | The text does not state a threat of injury to the speaker's addressee with the section's alarm/compulsion element. |

The queue also contains many short legal questions, near duplicates and accounts with essential facts omitted. For example, `TRIAGE_00003` says only that someone “stole” a phone and asks what punishment means; it does not describe the taking. This style is weak as a complaint-to-section training target.

## Decision

**Do not import any publisher-supplied positive label from this file.** The source file remains hash-pinned in quarantine. On 17 September 2026, `data_drafts/triage_review_batch01.jsonl` recorded decisions for all 104 in-scope queued rows: 21 short source rows were independently relabelled and accepted as train-only examples (7 possible matches, 10 insufficient-information, 4 out-of-scope); 83 were held. The accepted rows retain original row IDs, source license and hash, review rationale, and a source-text link in the master database. These short examples add phrasing diversity but are not a substitute for detailed complaints.

The relevant source checks are the [official BNS 2023 PDF](https://www.indiacode.nic.in/indiacode/bitstream/123456789/20062/1/a202345.pdf), particularly sections 304, 316 and 351, and the current verified text in `db/master_dataset.sqlite`.
