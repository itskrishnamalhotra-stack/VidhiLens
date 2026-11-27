# Fast route to full BNS/IT offence coverage

19 September 2026. Owner: Krishna Malhotra.

**Current update:** The counts below describe the earlier v12 planning
snapshot. Part 2 has since added missing-fact triage coverage for all 297
offence sections and 605 section-conditioned checks. The current research
export is v14 and the current complaint bundle is v8. See
[`PART2_COMPLETION.md`](PART2_COMPLETION.md) for current counts and limits.

## Correction to the earlier approach

The `5 train / 1 development / 2 sealed` per-section floor was a project planning
heuristic, not a legal or machine-learning requirement. Requiring it before a
first model experiment creates 1,655 additional positive cases across 256
sections. It does not itself demonstrate correct reasoning and would encourage
repetitive synthetic examples. Keep the floor as a diagnostic, not a claim
that a section is reliable when it is met.

## What can be completed in one pass

The full source-checked, in-force offence catalog is already available:
297 sections (278 BNS, 19 IT Act), each with pinned text, page, source ID,
text hash and a recommendation flag. `exports/full-offence-catalog-v2/`
exports it as one JSONL plus a hash manifest. The retrieval text excludes the
uncommenced BNS 106(2) while retaining the full text and a separate subpart
status record for provenance. This gives a later retrieval
component access to every eligible statute section without requiring a LoRA
to memorise 297 provisions. As of the v12 research export, all 297 have at
least two research positives. The earlier 188 single-positive gap was filled
with a versioned train-only batch; five overbroad first drafts were then
superseded in the complaint-only candidate export.

The current research training pool has 3,870 complaint triage cases, 5,259
grounded legal Q&A cases, and 52 workflow records. These are separate tasks
and must be mixed deliberately when a Colab experiment is eventually run.
The conservative complaint-only candidate in
`exports/complaint_only_v4_research_candidate/` keeps 3,604 triage and 52
workflow train records, covers all 297 offences with at least two positive
training cases, and excludes 266 weak or superseded triage records. It is not a legal accuracy
certificate or a final training release.
Nine QA train rows referring to omitted, unresolved, or uncommenced law were excluded in the v9 export. The app may suggest only the 19 sections with the existing recommendation
approval until wider evaluation passes.

## Bulk source review result

`profile_qa_incident_candidates.py` screened all 5,268 grounded legal Q&A
train records. It found 296 incident-like candidate questions across 163
offence sections. A stricter wording and commencement screen retained 148 candidate rows
across 105 of the 256 count-floor-gap sections. These are useful review leads,
not automatically correct complaint labels. Some ask about punishment,
omit an offence element, or include an old IPC reference. They cannot fill
the entire gap without new source-grounded cases.

`prepare_bulk_coverage_packets.py` placed all 256 gap sections in two
128-section JSONL packets. Each includes official verified text, current
positive cases, exact count deficits, and any strict Q&A candidates. The first
half contains all 105 sections with strict Q&A leads. Two BNS 106 questions
were excluded because they involve an uncommenced subpart. This removes repeated
per-section retrieval and lets case authoring and review happen in large
batches. The packets themselves approve zero new examples.

The 47,329-row `ri2000/Complaint_and_Sections` source still has no local file
in this workspace. Its public page requires an access grant and it uses IPC
labels. If access arrives, screen it as another candidate pool; do not bulk
convert its labels to BNS without checking the actual facts and changed law.

## Development-only retrieval check

A fixed character TF-IDF screen on the current 41 positive development
complaints retrieved the gold section in the top five for 26/41 cases using
statute text alone and 37/41 using positive training complaints as prototypes.
There were 41 distinct gold sections. The 55 additional sealed examples and
the 80 legacy sealed examples were not read or used. This is a small retrieval
diagnostic, not a model accuracy claim. It supports keeping source-grounded
training examples alongside the full statute catalog. See
`review_automation/retrieval_feasibility_v1/summary.json`.

## Fastest trustworthy next sequence

1. Freeze the full verified offence catalog and the current trainer-format
   research export. Keep publisher candidates quarantined.
2. Review the 148 strict Q&A leads in one pass against the packet statutes.
   Accept only fact-complete, privacy-safe train examples. Keep all of these
   source-derived leads out of dev/sealed because their Q&A versions are
   already in training.
3. Author genuinely new complaints, missing-fact cases and held-out cases in
   larger packets, prioritising sections where there is no fact-complete
   example. Run the one-command `process_coverage_batch.py` pipeline once per
   large packet, not once per three sections.
4. Train the first Colab adapter only after the selected dataset freeze. Give
   it retrieved law text at inference. Test unseen complaint families across
   both Acts, including abstention and wrong-section decoys. Expand case data
   where these tests show actual errors.
5. Raise an app section's recommendation gate only when its source status,
   fact-specific labels and held-out results support it. Count floors alone
   never enable a section.

This route can prepare all 256 sections in one pass and may substantially
reduce needless example writing. It cannot certify all 256 complaint labels
in one automated run with the presently available sources. That claim would
require treating weak or unreviewed data as legal truth.
