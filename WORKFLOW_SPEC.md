# Guided intake and complaint-draft contract

Version 1, 16 September 2026. Design specification for Phases 2–4; no live filing integration is part of v1.

## Data kept separate

- `user_narrative`: the user's original words, never silently overwritten.
- `reported_facts`: field, value, state (`present`, `absent`, `unknown`, `disputed`), and the user turn that supplied it. A selected option is a reported fact, not independently verified evidence.
- `analysis`: candidate provision IDs, reasons linked to reported facts, uncertainty, source snapshot IDs and model/KB version.
- `draft`: an unsaved local complaint text with version number and field-level change history.
- `saved_record`: exists only after explicit final confirmation and carries an internal project reference, not a government complaint number.

## Permitted model-proposed actions

| Action | Input/output contract | App integrity check |
| --- | --- | --- |
| `ask_question` | One useful missing fact, short prompt, options plus `Other` and `Not sure`, free text accepted | Option selection is stored as reported; no invented verification |
| `analyze_complaint` | Original narrative + reported facts -> candidate IDs, fact-linked reasons, status | IDs must be in current eligible KB; quotes hydrate from DB only |
| `show_results` | Ranked eligible sections or abstention with reason and sources | No invalid, blocked or unsourced ID displayed |
| `offer_draft` | Conversational offer after a plausible in-scope analysis | Offer itself never saves or submits anything |
| `collect_draft_details` | Ask only for missing fields needed to make a useful record | Unknown may remain unknown; do not fabricate a value |
| `create_draft` | Unsaved preview built from the user's facts and analysis | Show full preview and separate confirm/edit/cancel controls |
| `apply_draft_patch` | Exact requested field paths and old/new values | Reject unknown fields, conflicting version or ambiguous edits; preserve all other fields |
| `confirm_save` | User's explicit final confirmation for the current draft version | Save locally only if current version is confirmed and a reviewed eligible provision still applies |
| `cancel_draft` | User declines or cancels | Discard unsaved draft without a saved complaint reference |
| `delete_saved_record` | User requests deletion of a locally saved record | Delete according to app retention policy; no official portal effect |
| `refer_to_authorities` | Explain uncertainty/out-of-scope and point to appropriate channels | Do not call a person's report false, trivial or unworthy |

The model chooses when a follow-up or draft offer is useful; the app enforces data integrity, legal allowlisting and consent. The model must not treat `iOS` versus `Android` as a theft-law element. It may ask device type to improve the draft or recovery description.

## State transitions

`incident_entered` -> `analyzing` -> one of `ask_missing_fact`, `show_possible_sections`, `explain_uncertainty`.

A possible in-scope result may lead to `offer_draft` -> `collect_details` -> `draft_preview` -> `edit_preview` (repeat) -> `confirmed_local_save` or `cancelled`.

If any edit changes legally relevant facts, return to `analyzing` before another final confirmation. If an edit makes all provision matches invalid, the app must not save it as an in-scope complaint record under the earlier result. It may still let the user copy their own unsaved narrative.

## Example families needed for training and testing

- Useful follow-up versus needless follow-up; multiple-choice answer, free text, Other, Not sure and corrected answer.
- Immediate user request to register a complaint, with analysis and consent steps still respected.
- Positive result with one or more eligible sections; insufficient facts; out-of-scope; no valid candidates; conflicting reports.
- Precise edit of date, location, property, person, device, sequence and contact details; ambiguous edit; edit that changes the section recommendation; untouched fields preserved.
- Confirm only after final preview; cancel before save; delete after local save; no claim of police filing.
- Prompt-injection text inside the complaint, stale source IDs and unsupported model confidence.

## Official reporting boundary

The [National Cyber Crime Reporting Portal](https://www.cybercrime.gov.in/Webform/FAQ.aspx) is an official external reporting service. An internal reference number from this project is not an official police/cybercrime reference. If a future version connects to a government portal, that is a separate product and legal/technical authorization decision. The [portal's own notice](https://cybercrime.gov.in/Webform/Accept.aspx) directs emergencies and non-cyber crimes to local police and lists police helpline 112 and cyber helpline 1930.
