# Complaint dataset and labeling guide

Version 1, 16 September 2026. Owner: Krishna Malhotra. This guide defines how to prepare an academic dataset; it does not turn draft examples into legal opinions.

## Unit of data

One `scenario` is one distinct fictional incident, not one paraphrase. It has: original complaint text, language, provenance, privacy status, scenario group, expected outcome, facts present/absent/unknown/disputed, candidate provision labels, rationale, missing facts, review tier, reviewer/date, and split. `scenario_group` keeps paraphrases, translations and edited versions of the same incident together. One scenario may have multiple plausible sections.

`possible` means the stated facts make a provision worth considering within this project. It does **not** mean an offence is proven. `unsupported` means a necessary element is contradicted or absent in the stated facts. `uncertain` means a necessary fact is unknown or disputed. `insufficient_information` and `out_of_scope` are valid scenario outcomes with no forced positive label. Record the exact fact that would change an uncertain label.

## Legal issue matrix for draft examples

| Section | Ask/check in examples | Closest confusion to test |
| --- | --- | --- |
| BNS 75 | Specific act, unwanted nature, woman/man conditions in the text, and which clause | Ordinary rude conduct without the stated sexual act |
| BNS 77 | Watching/capturing/disseminating, private act, expectation of privacy, consent to capture versus sharing | General photograph without a private act |
| BNS 78 | Repeated contact despite clear disinterest or monitoring electronic communication; statutory exceptions | One unwanted contact with no monitoring |
| BNS 115 | Intent/knowledge, bodily pain/disease/infirmity, whether a statutory exception may matter | Mere argument with no hurt; compare BNS 117 |
| BNS 117 | Intent/knowledge of grievous hurt and a qualifying type of grievous hurt under BNS 116 | Ordinary hurt that does not meet BNS 116 |
| BNS 303 | Movable property, possession, consent, movement, dishonest taking | Lost item, permission, civil ownership disagreement |
| BNS 304 | Theft plus sudden/quick/forcible seizure from a person or possession | Ordinary unattended-property theft |
| BNS 316 | Entrustment/dominion and dishonest misappropriation/use/disposal | Failure to repay a normal debt without entrustment |
| BNS 318 | Deception and inducement or resulting likely harm; whether dishonest intent existed at the relevant time | Mere broken promise without evidence of deception |
| BNS 319 | Cheating by pretending to be another person or substituting identity | Use of own identity in a disputed transaction |
| BNS 329 | Entry or unlawful remaining plus intent to offend/intimidate/insult/annoy; dwelling if house-trespass | Accidental entry or lawful presence without such intent |
| BNS 351 | Threatened injury and intent to alarm or compel/stop an act; what exactly was threatened | Insult or criticism without threat |
| ITA 65 | Knowing/intended alteration/concealment/destruction of source code legally required to be kept | Ordinary deletion of code with no legal retention requirement |
| ITA 66 | A specific ITA 43 act plus dishonest/fraudulent mental state | Authorized system use or mere technical fault |
| ITA 66B | Stolen computer resource/device, receipt/retention, dishonest knowledge or reason to believe | Good-faith purchase without known warning facts |
| ITA 66C | Use of another person's signature/password/unique ID and dishonest/fraudulent state | Using one's own credential |
| ITA 66D | Cheating by personation through a communication device or computer resource | Online dispute without impersonation/deception |
| ITA 67 | Publishing/transmitting electronic material and the statutory obscenity threshold | Private possession or offensive but non-obscene speech |
| ITA 67A | Publishing/transmitting electronic material containing a sexually explicit act/conduct | Mere allegation without content or transmission facts |

ITA 66E is held and cannot be a positive label. BNS 114 and 116 and ITA 43 are support text, not standalone criminal suggestions. ITA 66A and 72A are blocked; BNS 106(2) is uncommenced in the pinned commencement notice. Public data that uses these as current criminal complaint labels must be rejected or corrected only after an explicit source check.

A phone being iOS or Android can help a complaint draft or recovery details. It is **not itself a legal element of theft**. Ask it when useful to record the incident, not as a prerequisite for choosing BNS 303 or 304. A user-selected option is reported information; do not describe it as independently verified.

## Coverage and review plan

1. Draft about 100 distinct fictional pilot incidents first, across all 19 enabled sections, confusable near misses, multi-issue incidents, insufficient facts, and matters outside the two-Act scope. Record language separately and check every translation against the same facts.
2. Before final training, aim for 300 distinct reviewed scenarios, including at least 60 abstention/out-of-scope incidents and 80 sealed-test incidents. Expand toward 500 only if time and review quality permit. These are quality targets, not a claim that the rows exist today.
3. Split by scenario group before any paraphrase or translation. Keep each incident family in exactly one of train, dev or sealed test. Silver variations are train-only. Never tune thresholds, prompts or model settings on sealed-test answers.
4. Codex performs the reviews. For each candidate, compare its facts with the pinned statutory excerpt and source page; check the suggested label, missing elements, alternate provisions, privacy, provenance and wording. Record the reviewer as `Codex AI source-grounded review`, with date and a short reason. Use `ai_reviewed`, never `self_reviewed` or `independently_reviewed`. Exclude unresolved examples from training and evaluation. An AI review does not certify legal correctness.
5. For an accepted `provision_match`, require at least one reviewed `possible` label using a currently recommendable ID. For abstention outcomes, require no possible label. Reject or hold any example with invented names, dates, evidence or quoted statements.
6. Keep the original complaint separate from a corrected draft. For a draft edit example, store the user edit request, exact field-level patch, unchanged fields, revised preview, and whether legal reanalysis is needed. Add confirm, cancel, ambiguous edit, and user-declines scenarios. No example should depict the app as actually submitting to police.
7. Export for Colab only after a dataset card, counts by section/outcome/language, license/privacy ledger, duplicate check, split manifest and reviewer records pass. Pin each export hash. Do not include quarantined online files by default.

## Outcome and conversation actions

The model may propose `ask_followup`, `show_results`, `offer_draft`, `draft`, `edit_draft`, `confirm_draft`, `cancel_draft`, `explain_uncertainty`, or `refer_to_authorities`. The app's structured checks ensure section IDs exist, draft patches touch only allowed fields, and explicit user confirmation precedes local saving. The model should choose when to ask or offer a draft from the facts, rather than follow a fixed keyword script. No response should call a user or report “not genuine” simply because this narrow system is uncertain or out of scope.
