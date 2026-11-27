"""Write fictional, unreviewed scenario drafts for the Phase 2 labeling queue.

These are candidate fact patterns, not approved examples or legal conclusions.
"""

from __future__ import annotations

import json
import sqlite3

from build_full_kb import DB_PATH, ROOT


SEEDS = [
    ("BNS_75", "A man at work repeatedly made sexually coloured remarks to a woman after she told him to stop.", "provision_match"),
    ("BNS_77", "A man secretly recorded a woman while she was changing clothes in a private room and sent the video to others.", "provision_match"),
    ("BNS_78", "A man kept contacting a woman to start a relationship after she clearly told him several times that she was not interested.", "provision_match"),
    ("BNS_115", "During a dispute, a person deliberately punched me and caused pain and swelling, but no fracture has been reported.", "provision_match"),
    ("BNS_117", "A person struck my arm with an iron rod saying he would break it. A hospital X-ray reported a fracture.", "provision_match"),
    ("BNS_303", "Someone took my phone from my desk without my permission and later said they intended to keep it.", "provision_match"),
    ("BNS_304", "A stranger suddenly grabbed my bag from my hand and ran away with it.", "provision_match"),
    ("BNS_316", "I entrusted money to a person to deposit for me, but they used it for themselves instead.", "provision_match"),
    ("BNS_318", "A seller took my payment for a phone after falsely claiming to own it; messages suggest the seller never had any phone to sell.", "provision_match"),
    ("BNS_319", "Someone pretended to be my employer and tricked me into sending money to an account they controlled.", "provision_match"),
    ("BNS_329", "A person entered my occupied home without permission to threaten me and refused to leave when asked.", "provision_match"),
    ("BNS_351", "A person threatened to burn my house unless I withdrew a complaint, and I was frightened by the threat.", "provision_match"),
    ("ITA_65", "An employee intentionally deleted computer source code that our organisation is legally required to preserve.", "provision_match"),
    ("ITA_66", "Someone entered our computer system without permission and dishonestly copied confidential files.", "provision_match"),
    ("ITA_66B", "A person kept a stolen phone after the seller told them it was stolen, and they planned to resell it.", "provision_match"),
    ("ITA_66C", "Someone dishonestly used my password to access my account without my permission.", "provision_match"),
    ("ITA_66D", "A caller pretending to be a bank employee used a mobile app message to trick me into sending money.", "provision_match"),
    ("ITA_67", "Someone posted text online that I believe is obscene. I can provide the post, but I need help describing its exact content.", "insufficient_information"),
    ("ITA_67A", "Someone uploaded a sexually explicit video of an adult to a public website without the person's permission.", "provision_match"),
    ("BNS_303", "I cannot find my phone. I last saw it at home, but I do not know whether it was taken or misplaced.", "insufficient_information"),
    ("BNS_303", "A person took my unattended bag from a table while I was away; nobody grabbed it from me.", "provision_match"),
    ("BNS_318", "A shop promised delivery next week, then missed the date; I do not know whether the seller deceived me when taking payment.", "insufficient_information"),
    ("BNS_78", "A person sent me one unwanted message. There has been no repeated contact or monitoring that I know of.", "out_of_scope"),
    ("ITA_66A", "Someone sent a rude message, so I want the app to use IT Act section 66A.", "out_of_scope"),
    ("ITA_66E", "Someone took a photograph that may invade privacy; I want the app to use IT Act section 66E.", "insufficient_information"),
    ("BNS_75", "A man demanded a sexual favour from a woman as a condition for helping her with a work request.", "provision_match"),
    ("BNS_77", "A woman agreed to be photographed in a private act but did not agree to publication; the photographer posted the image online.", "provision_match"),
    ("BNS_78", "A man monitored a woman's email use without her permission after she had asked him to stop contacting her.", "provision_match"),
    ("BNS_115", "A person deliberately slapped me during an argument, causing pain but no reported grievous injury.", "provision_match"),
    ("BNS_117", "Someone intentionally struck my leg with a bat and the medical report describes a bone fracture.", "provision_match"),
    ("BNS_303", "A neighbour borrowed my bicycle with permission but has not returned it, and I do not know what they intended when taking it.", "insufficient_information"),
    ("BNS_304", "A stranger grabbed the phone from my hand while I was speaking on it and fled.", "provision_match"),
    ("BNS_316", "I entrusted an employee with stock for delivery, but they sold it and kept the money for themselves.", "provision_match"),
    ("BNS_318", "A person sent me a fabricated payment receipt to induce me to hand over an item without actual payment.", "provision_match"),
    ("BNS_319", "A person pretended to be my relative and deceived me into transferring money to them.", "provision_match"),
    ("BNS_329", "A customer entered my shop during business hours and complained rudely, then left when asked.", "out_of_scope"),
    ("BNS_351", "Someone said they would injure my brother unless I stopped pursuing a lawful claim, and I was alarmed.", "provision_match"),
    ("ITA_65", "A contractor knowingly altered archived source code that a regulation requires us to maintain unchanged.", "provision_match"),
    ("ITA_66", "A former employee without authorization intentionally deleted data from our computer system to cause us a loss.", "provision_match"),
    ("ITA_66B", "I bought a used phone cheaply and later learned that it may have been stolen; I did not know this at purchase and want to explain the sequence.", "insufficient_information"),
    ("ITA_66C", "Someone used my unique login credentials to access my account and make changes without my permission.", "provision_match"),
    ("ITA_66D", "A person made a fake online store page using another business's identity and deceived customers into paying them.", "provision_match"),
    ("ITA_67", "A person publicly posted text online describing sexual activity in graphic detail to arouse readers; I can provide the exact post for review.", "provision_match"),
    ("ITA_67A", "Someone transmitted a video depicting an adult sexually explicit act to a large messaging group without permission.", "provision_match"),
    ("BNS_303", "My neighbour plays loud music late at night; no property was taken or threatened.", "out_of_scope"),
    ("BNS_318", "A genuine seller delayed delivery of an item because of a courier problem and has offered a refund.", "out_of_scope"),
    ("BNS_316", "I lent a friend money under a normal loan agreement and they have missed a payment; no entrusted property was involved.", "out_of_scope"),
    ("ITA_66", "My laptop stopped working after an update, but I have no evidence that anyone accessed or changed it without permission.", "insufficient_information"),
    ("BNS_351", "Someone said something upsetting about me, but I cannot remember their words or whether they threatened any injury.", "insufficient_information"),
    ("ITA_66C", "A coworker used a shared account password, but I do not know whether they had authorization to use it.", "insufficient_information"),
    ("BNS_303", "A person took my phone from my bag without consent and later used my password to access my online account.", "provision_match"),
    ("BNS_304", "A stranger snatched my bag from my hand and struck me while escaping, causing pain.", "provision_match"),
    ("ITA_66D", "A person used a fake bank identity in online messages to deceive me into sending money.", "provision_match"),
    ("BNS_77", "A person secretly captured an intimate private act and later shared the sexually explicit video online.", "provision_match"),
    ("BNS_78", "A man repeatedly followed a woman after she made clear she wanted no contact and then threatened to injure her if she reported him.", "provision_match"),
    ("BNS_115", "I disagree with my landlord about a deposit. Nobody used force, took property, or made a threat that I can describe.", "out_of_scope"),
    ("ITA_67A", "Someone says an intimate clip exists, but I do not know what it depicts or whether anyone uploaded or transmitted it.", "insufficient_information"),
]


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    allowed = {row[0] for row in conn.execute("SELECT provision_id FROM recommendable_provision")}
    rows = []
    for i, (focus_id, complaint, outcome) in enumerate(SEEDS, 1):
        rows.append({
            "draft_id": f"SEED_{i:03d}",
            "scenario_group": f"SEED_FAMILY_{i:03d}",
            "complaint_text": complaint,
            "language": "en",
            "provenance_type": "synthetic",
            "focus_id": focus_id,
            "focus_id_recommendable": focus_id in allowed,
            "candidate_outcome": outcome,
            "candidate_label": "possible" if outcome == "provision_match" and focus_id in allowed else "uncertain_or_unsupported",
            "quality_status": "pending_review",
            "review_tier": "pending_review",
            "split": None,
            "note": "Fictional draft only. Review facts, alternative sections, wording, and outcome before import.",
        })
    out = ROOT / "data_drafts" / "seed_scenarios.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} pending-review fictional seed drafts to {out}")


if __name__ == "__main__":
    main()
