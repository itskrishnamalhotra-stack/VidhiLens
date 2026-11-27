"""Author-reviewed, distinct complaint cases for nine previously uncovered sections.

Three train, one dev and two locally sealed cases per section. No surface
variation multiplier. This research expansion does not enable app suggestions.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "data_drafts" / "gap_examples_v2"
SYSTEM = ("Read the reported incident. Return JSON only with outcome, "
          "possible_provision_ids, and uncertain_sections. A section is only a "
          "possibility, never a finding of guilt. Never invent missing facts.")
WORKFLOW_SYSTEM = ("Continue this complaint-intake conversation. Return JSON only with "
                   "assistant_action, assistant_message, and tool_payload. Treat selected "
                   "options as reported facts, never verified facts. Do not claim an official "
                   "filing; save a local draft only after explicit confirmation.")

# Each group is two positive train cases, one missing-fact train case, one
# positive dev case, one positive sealed case, one missing-fact sealed case.
CASES = {
    "BNS_109": (
        "A person said they intended to kill my brother, aimed a loaded gun at his chest and fired. The bullet missed him, and witnesses saw the shot.",
        "After saying she would kill a neighbour, a person put poison in the neighbour's meal and placed it on their dining table. The meal was discovered before anyone ate it.",
        "A person bought a knife and said they might kill my cousin. I do not know whether they approached or attacked him.",
        "A person announced an intention to kill a shopkeeper and fired at the shopkeeper from a short distance. The shopkeeper survived with a wound.",
        "Someone aimed a firearm at my friend after saying they would kill him and pulled the trigger. The gun misfired, and two people witnessed it.",
        "My colleague heard that someone placed a meal at her door after making a threat to kill her. We do not know whether the meal was poisoned or who placed it there.",
        "whether_an_act_beyond_preparation_was_committed",
    ),
    "BNS_124": (
        "A person deliberately threw a corrosive liquid at my sister's face to disfigure her. Hospital records show burns and scarring.",
        "A man said he would permanently burn a neighbour's skin and threw acid at her. It missed her, and witnesses saw the attempt.",
        "A liquid splashed onto my friend's arm during an argument and caused a burn. I do not know whether it was thrown deliberately or spilled by accident.",
        "Someone intentionally poured a corrosive substance on a victim's hand to injure it. A clinician documented partial damage to the hand.",
        "A person tried to throw acid at my cousin while saying they wanted to scar her. The container fell before the liquid reached her.",
        "My neighbour developed a burn after a bottle broke nearby. I cannot tell who broke it or whether anyone meant to hurt her.",
        "whether_the_substance_was_used_intentionally_to_cause_the_specified_injury",
    ),
    "BNS_140": (
        "Two people forcibly took my brother away, confined him, and called us demanding a ransom while threatening to hurt him if we refused.",
        "A person abducted a student and kept her in a locked room. They threatened to kill her unless her family paid the demanded money.",
        "My relative has not returned home, and an unknown caller asked for money. I cannot establish whether anyone kidnapped or detained the relative.",
        "A group forced a passenger into a vehicle and later demanded payment from his family, saying they would injure him if the family did not pay.",
        "Someone carried a child away from school without permission and kept the child confined. They demanded a ransom from the child's parent and threatened harm.",
        "A witness says someone may have forced my friend into a car, and an unknown caller later demanded money. I cannot confirm who was in the car or whether my friend was detained.",
        "whether_the_person_was_kidnapped_or_abducted_and_detained_under_threat",
    ),
    "BNS_305": (
        "A visitor secretly took my laptop from inside my home without permission and carried it away intending to keep it.",
        "Someone removed my bag from a passenger train without my consent and left with it intending to keep it.",
        "My wallet was missing after a gathering at my apartment. I do not know if somebody took it or if I misplaced it.",
        "A person entered a warehouse used to store another person's goods, took a boxed camera without consent and sold it.",
        "Someone took an idol from a place of worship without permission, moved it away and tried to sell it.",
        "My bicycle disappeared, but I cannot tell whether it was taken from inside my locked garage or from the open street, or whether anyone moved it without consent.",
        "whether_property_was_dishonestly_taken_and_the_special_location_or_property_condition_applies",
    ),
    "BNS_308": (
        "A person threatened to injure my sister unless I handed over cash. Frightened by the threat, I gave that person the money.",
        "Someone threatened to publish a false damaging allegation about me unless I signed and delivered a payment promise. I signed and handed over the document because of that threat.",
        "An unknown account demanded money and mentioned a secret about me. I cannot tell whether the message threatened an injury or whether any payment was made.",
        "A caller threatened to hurt my father unless I transferred money. I made the transfer because I feared the threatened injury.",
        "A person threatened to damage my shop unless I gave them my jewellery. I handed it over because I was afraid they would carry out the threat.",
        "A message demanded money and said something bad would happen to my family if I refused. I do not know who sent it or what injury was being threatened.",
        "whether_a_threat_of_injury_dishonestly_induced_delivery_or_was_an_attempt_to_do_so",
    ),
    "BNS_309": (
        "A person blocked my path, showed a knife and demanded my wallet immediately. I handed it over because I feared instant harm.",
        "Someone held my brother down while taking cash from his pocket without consent, then ran away with it.",
        "A stranger took my parcel and ran away. I do not know whether they used force, restraint or a threat of immediate harm.",
        "A person struck me so they could take my bag, then carried it away without my consent while I was injured.",
        "A person threatened to stab a passenger on the spot and demanded a phone. The passenger handed over the phone immediately out of fear.",
        "My bag disappeared during a crowded scuffle. I cannot tell whether someone took it or whether anyone used force or an immediate threat to take it.",
        "whether_force_restraint_or_fear_of_instant_harm_accompanied_the_taking",
    ),
    "BNS_324": (
        "A neighbour deliberately smashed the windows of my parked car after saying they wanted to cause me financial loss.",
        "Someone intentionally cut the power cable to my machine knowing it would damage the machine and stop it working.",
        "My appliance stopped working after a visitor used it. I cannot tell whether they damaged it deliberately or it failed on its own.",
        "A person admitted destroying stock in my store to cause me loss, and photographs show the damaged goods.",
        "Someone deliberately scratched a rented vehicle to reduce its value and make its owner pay for repairs.",
        "My car window broke during a storm, but a neighbour says someone may have struck it shortly before. I cannot tell what caused the damage or whether anyone acted deliberately.",
        "whether_someone_intentionally_or_knowingly_caused_property_damage_or_loss",
    ),
    "ITA_67B": (
        "An adult sent a digital file depicting a child in sexually explicit conduct to an online group. I have the message and the child is under 18.",
        "A person used a computer account to solicit a child for an online sexual act. The child is 14 and saved the messages.",
        "I saw a disturbing image circulating online, but I cannot tell whether it depicts a child or the type of content involved.",
        "Someone created and distributed electronic images depicting a 16-year-old in sexually explicit conduct. The distribution messages were preserved.",
        "An adult used an app to facilitate sexual abuse of a child online. The saved conversation identifies the child as 15.",
        "A parent says a teenager received an inappropriate message. I have not seen its content or confirmed the teenager's age.",
        "whether_the_person_is_under_18_and_the_electronic_conduct_matches_section_67B",
    ),
    "ITA_70": (
        "A government notification identifies this network as a protected system. A former contractor knowingly tried to access it after written authorisation was withdrawn.",
        "A person obtained access to a computer resource officially notified as a protected system, although they had never been authorised to access it.",
        "Someone entered a government website without permission. I cannot establish whether that resource was officially notified as a protected system.",
        "A security log shows an unauthorised person repeatedly trying to access a system named in an official protected-system notification.",
        "An employee kept using credentials to enter a notified protected system after the written access order had been revoked.",
        "My workplace calls a server critical, but I have not found an official protected-system notification or the alleged user's access status.",
        "whether_an_official_notification_declares_the_resource_protected_and_access_was_unauthorised",
    ),
}

# Distinct workflow stories. Each user turn generates one training record with
# the full prior conversation so a later edit refers to the right draft version.
WORKFLOWS = [
    ("train", "robbery_draft", [
        ("A person held me down and took my wallet from my pocket. Can you help me make a complaint?",
         "offer_draft", "BNS 309 may apply to the reported force and taking. Would you like me to prepare a local complaint draft for your review?",
         {"candidate_provision_ids": ["BNS_309"], "requires_user_opt_in": True, "official_filing": False}),
        ("Yes, draft it, but do not save it yet.", "draft",
         "Draft, version 1: A person held me down and took my wallet from my pocket without my consent. This draft is unsaved. Please review, edit, confirm, or cancel.",
         {"draft_version": 1, "known_provision_ids": ["BNS_309"], "saved": False, "official_filing": False}),
        ("Change 'wallet' to 'phone'. I said the wrong item.", "edit_draft",
         "Draft, version 2: A person held me down and took my phone from my pocket without my consent. This draft is unsaved. Please review, edit, confirm, or cancel.",
         {"from_version": 1, "to_version": 2, "patch": {"field": "stolen_item", "old_text": "wallet", "new_text": "phone"}, "saved": False, "official_filing": False}),
        ("Version 2 is correct. Save that exact draft locally.", "confirm_draft",
         "I will save exactly version 2 as a local draft. It has not been filed with any authority.",
         {"command": "save_local_draft", "draft_version": 2, "explicit_user_confirmation": True, "require_current_version": True, "official_filing": False}),
    ]),
    ("train", "extortion_clarification", [
        ("Someone is asking me for money and saying I will regret refusing. Is this extortion?",
         "ask_followup", "What harm did the person threaten, and did you hand over money or another item because of that threat?",
         {"candidate_provision_ids": [], "uncertain_provision_ids": ["BNS_308"], "missing_facts": ["threatened_injury", "delivery_or_attempt"], "official_filing": False}),
        ("They threatened to break my arm, and I transferred money because I was afraid.",
         "suggest_provisions", "Given the reported threat and transfer, BNS 308 may be relevant. This is a possible section, not a finding that an offence occurred.",
         {"candidate_provision_ids": ["BNS_308"], "reported_facts": ["threat_of_injury", "money_transferred_due_to_fear"], "official_filing": False}),
        ("Please prepare a complaint draft, but I may change it.", "draft",
         "Draft, version 1: A person threatened to break my arm unless I transferred money. I transferred money because I feared that threat. This draft is unsaved; review, edit, confirm, or cancel it.",
         {"draft_version": 1, "known_provision_ids": ["BNS_308"], "saved": False, "official_filing": False}),
    ]),
    ("train", "theft_cancel", [
        ("Someone took my laptop from inside my home without permission and carried it away. Can we draft a complaint?",
         "offer_draft", "BNS 305 may be relevant because the reported theft was from a dwelling. Would you like a local draft?",
         {"candidate_provision_ids": ["BNS_305"], "requires_user_opt_in": True, "official_filing": False}),
        ("Yes, prepare it without saving.", "draft",
         "Draft, version 1: Someone took my laptop from inside my home without permission and carried it away. This draft is unsaved.",
         {"draft_version": 1, "known_provision_ids": ["BNS_305"], "saved": False, "official_filing": False}),
        ("Cancel the draft. I found the laptop with my roommate and need to check what happened.", "cancel_draft",
         "I have cancelled the unsaved draft. I will not treat the taking as established while the facts are unclear.",
         {"command": "discard_local_draft", "draft_version": 1, "saved": False, "official_filing": False}),
    ]),
    ("dev", "damage_edit", [
        ("A person intentionally smashed the window of my parked vehicle to cause me loss. Help me draft this.",
         "offer_draft", "BNS 324 may be relevant to the reported intentional damage. Would you like an unsaved local draft?",
         {"candidate_provision_ids": ["BNS_324"], "requires_user_opt_in": True, "official_filing": False}),
        ("Yes, make the draft.", "draft",
         "Draft, version 1: A person intentionally smashed the window of my parked vehicle to cause me loss. This draft is unsaved.",
         {"draft_version": 1, "known_provision_ids": ["BNS_324"], "saved": False, "official_filing": False}),
        ("Change 'window' to 'windscreen'. That is the damaged part.", "edit_draft",
         "Draft, version 2: A person intentionally smashed the windscreen of my parked vehicle to cause me loss. This draft is unsaved.",
         {"from_version": 1, "to_version": 2, "patch": {"field": "damaged_part", "old_text": "window", "new_text": "windscreen"}, "saved": False, "official_filing": False}),
    ]),
    ("sealed_test", "protected_system_uncertainty", [
        ("A former employee accessed our server after leaving the company. Does IT Act section 70 apply?",
         "ask_followup", "Was this computer resource officially notified as a protected system, and was the former employee authorised to access it at that time?",
         {"candidate_provision_ids": [], "uncertain_provision_ids": ["ITA_70"], "missing_facts": ["official_protected_system_notification", "written_access_authorisation"], "official_filing": False}),
        ("The server was never officially notified as protected. We only called it critical internally.",
         "ask_followup", "That does not establish IT Act section 70. Was access unauthorised, and was any data copied, changed, damaged or used dishonestly? Those facts may matter for a different section.",
         {"candidate_provision_ids": [], "section_70_supported": False, "uncertain_provision_ids": ["ITA_66"], "missing_facts": ["unauthorised_access", "data_or_system_effect", "dishonest_or_fraudulent_intent"], "save_allowed": False, "official_filing": False}),
    ]),
]


def norm(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    conn = sqlite3.connect(DB)
    existing = {norm(r[0]) for r in conn.execute("SELECT complaint_text FROM scenario")}
    official = {}
    for pid in CASES:
        row = conn.execute("SELECT legal_status,provision_kind,verified_text,source_pdf_page "
                           "FROM provision WHERE provision_id=?", (pid,)).fetchone()
        if not row or row[0] != "in_force" or row[1] != "offence" or not row[2] or not row[3]:
            raise ValueError(f"Section source/status not ready: {pid}")
        official[pid] = {"source_pdf_page": row[3], "verified_text_sha256": sha(row[2])}
    OUT.mkdir(parents=True, exist_ok=True)
    output = {s: [] for s in ("train", "dev", "sealed_test")}
    seen = set(existing)
    for pid, cases in CASES.items():
        if len(cases) != 7:
            raise ValueError(f"Expected six cases and missing-fact key: {pid}")
        *texts, missing = cases
        for index, text in enumerate(texts):
            key = norm(text)
            if key in seen: raise ValueError(f"Repeated case: {pid}/{index}")
            seen.add(key)
            split = "train" if index < 3 else "dev" if index == 3 else "sealed_test"
            uncertain = index in (2, 5)
            target = {"outcome": "insufficient_information" if uncertain else "provision_match",
                      "possible_provision_ids": [] if uncertain else [pid],
                      "uncertain_sections": [{"provision_id": pid, "missing_facts": missing}] if uncertain else []}
            output[split].append({"id": f"gap-v2-{pid}-{index+1}",
                                  "messages": [{"role": "system", "content": SYSTEM},
                                               {"role": "user", "content": text},
                                               {"role": "assistant", "content": json.dumps(target, separators=(",", ":"))}],
                                  "metadata": {"kind": "triage", "target_provision_id": pid, "split": split,
                                               "source_pdf_page": official[pid]["source_pdf_page"],
                                               "verified_text_sha256": official[pid]["verified_text_sha256"],
                                               "review_status": "AI_authored_against_source_checked_section",
                                               "incident_family": f"{pid}_{index+1}",
                                               "uncertainty_case": uncertain}})
    for split, group, turns in WORKFLOWS:
        history = [{"role": "system", "content": WORKFLOW_SYSTEM}]
        for index, (user, action, message, payload) in enumerate(turns, 1):
            history.append({"role": "user", "content": user})
            target = {"assistant_action": action, "assistant_message": message,
                      "tool_payload": payload}
            assistant = {"role": "assistant", "content": json.dumps(target, ensure_ascii=False, separators=(",", ":"))}
            output[split].append({"id": f"gap-v2-workflow-{group}-{index}",
                                  "messages": history + [assistant],
                                  "metadata": {"kind": "workflow", "split": split,
                                               "conversation_group": group,
                                               "review_status": "AI_authored_workflow_case"}})
            history.append(assistant)
    for split, rows in output.items():
        with (OUT / f"{split}.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows: stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    report = {"sections_added_as_research_cases": list(CASES),
              "counts": {k: len(v) for k, v in output.items()},
              "counts_by_kind": {k: dict(Counter(r["metadata"]["kind"] for r in rows)) for k, rows in output.items()},
              "reason_not_in_pilot_export": "New sections are not yet approved for app recommendations or final-model training; source-checked research examples are separate.",
              "sealed_test_path": str(OUT / "sealed_test.jsonl"),
              "source": "Pinned official India Code PDFs in phase1/sources plus master DB verified_text and source pages",
              "files_sha256": {k: sha((OUT / f"{k}.jsonl").read_text(encoding="utf-8")) for k in output}}
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
