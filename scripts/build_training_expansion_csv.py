"""Write one inspectable CSV of fictional, family-derived training candidates.

Every family below is authored against the pinned eligible section text. The
24 surface variants per family change the actor and setting; they are not 24
independent legal fact patterns. Import keeps this distinction as silver tier.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "master_dataset.sqlite"

OUT = ROOT / "data_drafts" / "synthetic_training_expansion_v1.csv"

# Five independent fact patterns for each eligible section except ITA_65. Its
# legal-retention element is too easy to invent, so the existing reviewed cases
# remain its only positive training examples for now.
POSITIVE: dict[str, tuple[str, list[str]]] = {
    "BNS_115": ("physical", [
        "{actor} intentionally punched another person to cause pain. The punch caused immediate pain and a bruise; no serious injury is reported.",
        "{actor} said they wanted to hurt a neighbour and deliberately shoved that person into a wall. The neighbour felt pain and had a sore shoulder.",
        "{actor} slapped a customer during an argument intending to cause pain. The customer reported pain and visible redness afterward.",
        "{actor} deliberately kicked a coworker's shin after saying it would hurt. The coworker experienced pain and swelling, with no fracture reported.",
        "{actor} threw a small object at another person to hurt them. It struck the person's arm and caused pain and a temporary bruise.",
    ]),
    "BNS_117": ("physical", [
        "{actor} said they would break another person's arm and repeatedly struck it with a heavy stick. A medical report records an arm fracture.",
        "{actor} deliberately hit a person's leg with a hard object while saying they intended to break it. Hospital imaging later showed a leg fracture.",
        "{actor} announced an intention to permanently damage a person's sight and struck the eye. A medical examination records permanent loss of sight in that eye.",
        "{actor} threatened to disfigure a person's face permanently and then cut the face. A clinician recorded permanent facial disfigurement.",
        "{actor} repeatedly stamped on a person's hand after saying they would crush the bones. A hospital report records multiple hand fractures.",
    ]),
    "BNS_303": ("property", [
        "{actor} took a resident's unattended bicycle from the resident's possession without permission, moved it away, and said they planned to sell it for their own gain.",
        "{actor} quietly removed a shop owner's boxed tablet from a shelf without consent and carried it away intending to keep it.",
        "{actor} took cash from a colleague's closed desk without consent, moved it into a pocket, and later admitted intending to keep it.",
        "{actor} removed a neighbour's portable toolbox from the neighbour's storage area without permission and carried it home to sell.",
        "{actor} moved a visitor's parked scooter away without permission, intending to dispose of it for personal gain rather than return it.",
    ]),
    "BNS_304": ("property", [
        "{actor} suddenly grabbed a phone from a commuter's hand without consent and ran away intending to keep it.",
        "{actor} quickly pulled a handbag from a pedestrian's grasp and fled with it, despite the pedestrian trying to hold on.",
        "{actor} rapidly seized a wallet from a person's hand while the person was paying a fare, then escaped with it without permission.",
        "{actor} suddenly snatched a parcel from a courier's arms and ran away, intending to keep the parcel without the courier's consent.",
        "{actor} quickly grabbed a camera from a tourist's hands and fled, without consent and with the stated plan of selling it.",
    ]),
    "BNS_316": ("trust", [
        "{actor} was entrusted with association funds solely to pay a booked venue. Instead, they transferred the money to a personal account and spent it on private purchases.",
        "{actor} accepted a camera for safekeeping under an agreement to return it. They knowingly pawned it for personal cash instead.",
        "{actor} was entrusted with goods as a warehouse keeper and agreed to return them on demand. They dishonestly sold the goods and kept the proceeds.",
        "{actor} collected rent as an agent required to pass it to the property owner. They kept the collected money for personal use against that agreement.",
        "{actor} received a sealed parcel for delivery to its owner. Instead of delivering it, they opened and sold its contents for their own benefit.",
    ]),
    "BNS_318": ("deception", [
        "{actor} falsely claimed at the outset that a used machine had passed an inspection and showed a fabricated certificate. A buyer believed this and paid for the machine.",
        "{actor} knowingly displayed a counterfeit brand mark as genuine before a sale. The buyer relied on that false claim and paid for the product.",
        "{actor} knowingly showed a sample unlike the goods they intended to deliver. The buyer believed the sample represented the goods and paid in advance.",
        "{actor} knowingly lied that they owned equipment available for sale, though they did not own it and could not deliver it. A buyer relied on the claim and paid a deposit.",
        "{actor} falsely said a paid training course had a certification it never had. A student relied on that claim and paid the course fee.",
    ]),
    "BNS_319": ("personation", [
        "{actor} pretended to be a specific property owner, deceived a prospective tenant, and obtained a deposit for a flat they did not control.",
        "{actor} posed as a named supplier's authorised representative, falsely claimed payment was due to them, and induced a customer to hand over cash.",
        "{actor} impersonated a particular charity officer, deceived a donor about their identity, and obtained a donation intended for the charity.",
        "{actor} claimed to be a specific bank employee, deceived a customer into believing this, and induced the customer to hand over money.",
        "{actor} pretended to be the named owner of a bicycle, deceived a buyer about that identity, and induced payment for the bicycle.",
    ]),
    "BNS_329": ("property", [
        "{actor} entered another person's fenced yard without permission intending to frighten the person inside, and shouted that they had come to intimidate them.",
        "{actor} entered a resident's dwelling without permission intending to insult and intimidate the resident, and stayed after being told to leave.",
        "{actor} lawfully entered a shop but remained after permission was withdrawn, intending to intimidate its owner with aggressive conduct.",
        "{actor} entered a warehouse in another person's possession without consent intending to damage stored property, and began looking for the goods.",
        "{actor} climbed into a neighbour's courtyard without consent intending to annoy the neighbour, and admitted that purpose when confronted.",
    ]),
    "BNS_351": ("physical", [
        "{actor} threatened to burn another person's shop unless that person withdrew a lawful claim. The person was alarmed and saved the threat.",
        "{actor} threatened serious harm to a person's family member to force the person to pay money they did not owe. The threat caused alarm.",
        "{actor} said they would destroy a person's vehicle unless the person stopped pursuing a lawful complaint. The person was frightened by the threat.",
        "{actor} threatened to injure a coworker to make that coworker surrender a work document they were entitled to keep. The coworker felt alarmed.",
        "{actor} threatened to harm a person's reputation with a fabricated allegation unless the person signed a document. The threat caused alarm.",
    ]),
    "BNS_75": ("harassment", [
        "{actor} demanded a sexual favour from a woman in exchange for approving her request. She refused and reported the demand.",
        "{actor} deliberately showed pornography to a woman after she said she did not want to see it. She reported that the display was against her will.",
        "{actor} made sexually coloured remarks about a woman's body directly to her despite her objection. She recorded the words and date.",
        "{actor} made an unwelcome physical advance involving an explicit sexual overture toward a woman. She stepped away and reported what happened.",
        "{actor} asked a woman for sexual favours as a condition for giving her a work opportunity. She refused and saved the request.",
    ]),
    "BNS_77": ("privacy", [
        "{actor} secretly watched a woman changing clothes in a locked room where she expected privacy. She did not agree to being watched.",
        "{actor} concealed a camera to record a woman using a lavatory where she expected privacy. She found the recording device afterward.",
        "{actor} photographed a woman while she was undressing in a private room, without her knowledge or consent to being observed.",
        "{actor} shared an intimate image of a woman engaged in a private act. She had agreed to its original capture but had expressly refused sharing with others.",
        "{actor} used a hidden video feed to watch a woman during a private sexual act in a room where she expected not to be observed.",
    ]),
    "BNS_78": ("stalking", [
        "{actor} repeatedly followed a woman from her commute and tried to speak with her after she clearly said she did not want contact.",
        "{actor} used new accounts to send a woman requests for personal meetings every week after she blocked the earlier account and said she was not interested.",
        "{actor} repeatedly waited outside a woman's class and approached her to seek personal interaction despite her clear written refusal.",
        "{actor} secretly configured a woman's email to forward her private messages to them and later quoted those messages, showing monitoring of her electronic communication.",
        "{actor} installed software to monitor a woman's internet use without her knowledge and later described the pages she visited.",
    ]),
    "ITA_66": ("cyber", [
        "{actor} entered a company system without permission and dishonestly copied private customer data to sell it for personal gain.",
        "{actor} accessed a business server after access was revoked and deliberately deleted records to cause the business financial loss.",
        "{actor} introduced malicious code into a computer network without permission to disrupt operations and demand money to restore access.",
        "{actor} without permission disabled an authorised user's access to a company account, intending to cause financial loss and gain an advantage.",
        "{actor} without permission manipulated a computer billing system so services they used were dishonestly charged to another person's account.",
    ]),
    "ITA_66B": ("cyber", [
        "{actor} bought a stolen phone after the seller expressly said it was stolen, kept it, and planned to resell it for profit.",
        "{actor} received a stolen laptop whose owner had reported the theft, knew that fact, and retained the laptop for personal use.",
        "{actor} accepted a stolen tablet from a friend who admitted taking it without consent, then hid and kept the device.",
        "{actor} purchased a stolen communication device for an unusually low price after being told it came from a theft, then retained it dishonestly.",
        "{actor} received a stolen computer from another person, acknowledged in messages that it belonged to a theft victim, and sold it.",
    ]),
    "ITA_66C": ("cyber", [
        "{actor} used another person's password without permission to enter that person's account and dishonestly make a purchase.",
        "{actor} copied another person's electronic signature and fraudulently used it to approve a transaction in that person's name.",
        "{actor} used a coworker's unique account identifier without authority to dishonestly obtain a benefit allocated to that coworker.",
        "{actor} entered a former colleague's account using the colleague's password without consent to obtain private records for personal gain.",
        "{actor} fraudulently used another person's one-time login credential to access the person's account and transfer its stored balance.",
    ]),
    "ITA_66D": ("online", [
        "{actor} used an online account pretending to be a specific landlord, deceived a renter, and induced payment of a deposit for a flat they did not control.",
        "{actor} used a messaging app while impersonating a named charity officer, deceived a donor, and obtained a donation meant for that charity.",
        "{actor} used a computer account pretending to be a particular supplier, deceived a buyer, and induced payment for goods they had no authority to sell.",
        "{actor} posed as a specific bank employee in an online chat, deceived a customer about that identity, and induced a payment to them.",
        "{actor} used a phone account claiming to be the named owner of a vehicle, deceived a buyer, and induced a booking payment for that vehicle.",
    ]),
    "ITA_67": ("online", [
        "{actor} electronically posted a lascivious adult image designed to arouse sexual interest, without depicting a sexually explicit act, on a public page.",
        "{actor} transmitted an obscene illustrated adult image through an online group, with prurient content but no depicted sexual act.",
        "{actor} published a digital poster with lascivious adult imagery and sexually suggestive captions, but no sexually explicit act, for public viewing.",
        "{actor} sent an electronic file containing obscene adult drawings appealing to prurient interest, without any depicted sexual act, to a large group.",
        "{actor} uploaded a public page of lascivious adult images likely to deprave or corrupt viewers, while the material did not depict an explicit sexual act.",
    ]),
    "ITA_67A": ("online", [
        "{actor} uploaded a video showing sexually explicit conduct by adults to an electronic sharing service where others could view it.",
        "{actor} transmitted a digital recording of an explicit sexual act involving adults to an online group.",
        "{actor} published an electronic file depicting sexually explicit adult conduct on a public account. A viewer recorded the account name and the file link.",
        "{actor} sent multiple recipients an online link they had uploaded to a video file showing an explicit sexual act by adults.",
        "{actor} posted a digital clip depicting sexually explicit conduct by adults on a site accessible to other users.",
    ]),
}

# Uncertainty examples name the missing legal element; no positive label is given.
UNCERTAIN: list[tuple[str, str, str, str]] = [
    ("BNS_303", "property", "{actor} noticed that a phone was no longer where it had been left, but nobody knows whether it was lost, moved with permission, or taken dishonestly.", "Whether a person moved the phone dishonestly without consent"),
    ("BNS_304", "property", "{actor} reported a missing bag after a crowded journey but cannot say whether anyone suddenly seized it or whether it was left behind.", "Whether someone quickly seized the bag from a person or their possession"),
    ("BNS_316", "trust", "{actor} was holding association money for an event, and the balance is now unclear. No record yet shows whether any entrusted funds were dishonestly used.", "Whether entrusted money was dishonestly converted or used contrary to the trust"),
    ("BNS_318", "deception", "{actor} took payment for a delivery that is late. The buyer has no information about what the seller represented or intended when payment was taken.", "Whether the seller deceived the buyer at the time of payment"),
    ("BNS_319", "personation", "{actor} used a name resembling someone else's in a conversation, but it is unclear whether they pretended to be that person or induced anyone through deception.", "Whether the person claimed a false identity and cheated someone through it"),
    ("BNS_329", "property", "{actor} entered another person's compound, but the complainant does not know whether entry was permitted or whether the visitor intended intimidation, insult, annoyance, or another offence.", "Permission and the intent behind entry or remaining"),
    ("BNS_351", "physical", "{actor} made a vague angry comment about future trouble. The exact words and whether they were meant to cause alarm or coerce action are unknown.", "The actual threat and whether it was intended to alarm or compel conduct"),
    ("BNS_75", "harassment", "{actor} made an uncomfortable comment to a woman, but the complainant cannot repeat the words or describe whether it was sexually coloured or another listed act.", "The words or conduct needed to identify a listed sexual-harassment act"),
    ("BNS_77", "privacy", "{actor} shared an image of a woman, but the complainant has not seen it and cannot say whether it shows a private act or whether she expected privacy.", "Whether the image shows the woman in a private act under the statutory conditions"),
    ("BNS_78", "stalking", "{actor} has been seen near a woman's workplace, but it is unclear whether he followed or contacted her repeatedly after disinterest or monitored her communications.", "Repeated unwanted contact after clear disinterest or monitoring of electronic communication"),
    ("BNS_115", "physical", "{actor} and another person argued before the other person reported pain. Nobody can yet say whether an intentional or knowing act by the first person caused the pain.", "Whether the actor intentionally or knowingly caused bodily hurt"),
    ("BNS_117", "physical", "{actor} was present when a person later reported a fracture, but the complainant does not know who caused it or whether grievous hurt was intended or known to be likely.", "Causation and intention or knowledge regarding grievous hurt"),
    ("ITA_66", "cyber", "{actor} appeared in a computer login log, but permission, the act performed, and dishonest or fraudulent purpose have not been established.", "The unauthorised section 43 act and dishonest or fraudulent intent"),
    ("ITA_66B", "cyber", "{actor} bought a second-hand phone that was later reported stolen, but the buyer's knowledge or reason to believe it was stolen is unknown.", "Whether the buyer knew or had reason to believe the device was stolen"),
    ("ITA_67A", "online", "{actor} shared a video link, but the complainant has not viewed the video and cannot describe whether it contains sexually explicit conduct.", "Whether the electronic material contains a sexually explicit act or conduct"),
]

OUT_OF_SCOPE: list[tuple[str, str]] = [
    ("general", "{actor} wants to challenge a university timetable change. The report describes only scheduling and asks how to request another class slot."),
    ("general", "{actor} disputes an examination mark and asks for a recheck. The report contains no allegation of deception, threat, or other conduct within this pilot's sections."),
    ("general", "{actor} wants a streetlight repaired because it has not worked for several evenings. The report asks where to send a maintenance request."),
    ("general", "{actor} complains that a bus route was changed without enough notice. They seek the transport office's timetable and contact details."),
    ("general", "{actor} seeks a correction to a spelling error on a course certificate. The institution acknowledges the clerical error and offers a correction process."),
    ("general", "{actor} asks whether a shop can exchange an unused item under its published returns policy. No deception or dishonest taking is alleged."),
    ("general", "{actor} reports that a legitimate internet service has been slow under its advertised plan. The provider acknowledges a technical outage; no unauthorised computer act is alleged."),
    ("general", "{actor} wants to know how to apply for a municipal parking permit. The report describes no threat, dishonest taking, or other incident within this pilot's sections."),
    ("general", "{actor} seeks a copy of a previously issued receipt for a lawful purchase. The seller agrees the purchase occurred and no deception is reported."),
    ("general", "{actor} asks the apartment committee to change the timing of shared-facility cleaning. The complaint is about a routine management decision only."),
]

ACTORS = {
    "physical": ["a person", "an individual", "a visitor", "an acquaintance", "a local resident", "a passerby"],
    "property": ["a person", "an individual", "a visitor", "a worker", "a building contractor", "a stranger"],
    "trust": ["a person", "an individual", "a manager", "a worker", "a service provider", "an entrusted employee"],
    "deception": ["a seller", "a service provider", "a trader", "a shop operator", "a course organiser", "a dealer"],
    "personation": ["a stranger", "a seller", "a visitor", "a caller", "an intermediary", "a broker"],
    "harassment": ["a male coworker", "a male customer", "a male supervisor", "a male visitor", "a male instructor", "a male neighbour"],
    "privacy": ["a person", "an individual", "a visitor", "a staff member", "a former partner", "a building employee"],
    "stalking": ["a man", "a male coworker", "a male neighbour", "a former male acquaintance", "a male classmate", "a male visitor"],
    "cyber": ["a person", "an individual", "an employee", "a visitor", "a former colleague", "a reseller"],
    "online": ["an account holder", "a user", "a seller", "a stranger", "a former acquaintance", "a page administrator"],
    "general": ["a student", "a resident", "a customer", "a commuter", "a parent", "a worker"],
}

REPORT_FRAMES = (
    "The complainant reports that ",
    "The initial account says that ",
    "According to the complainant, ",
    "The written report states that ",
)

RATIONALES = {
    "BNS_115": "The account states an intentional act causing bodily pain or bruising.",
    "BNS_117": "The account states intended or known likely grievous hurt and a documented grievous result.",
    "BNS_303": "The account states dishonest movement of another's movable property from possession without consent.",
    "BNS_304": "The account states a sudden or quick seizure of movable property from a person or their possession in order to steal it.",
    "BNS_316": "The account states entrustment of property followed by dishonest conversion or use contrary to that trust.",
    "BNS_318": "The account states deception at the outset that induced a payment or other property delivery.",
    "BNS_319": "The account states cheating by pretending to be another person.",
    "BNS_329": "The account states entry or unlawful remaining on another's property with the specified intent.",
    "BNS_351": "The account states a threat of injury intended to alarm or compel conduct.",
    "BNS_75": "The account states conduct by a man toward a woman within a listed sexual-harassment act.",
    "BNS_77": "The account states watching, capture, or dissemination of an image of a woman engaged in a private act.",
    "BNS_78": "The account states repeated contact despite clear disinterest or monitoring of a woman's electronic communication by a man.",
    "ITA_66": "The account states an unauthorised section 43 computer act done dishonestly or fraudulently.",
    "ITA_66B": "The account states dishonest receipt or retention of a stolen device with knowledge or reason to believe it was stolen.",
    "ITA_66C": "The account states fraudulent or dishonest use of another person's password, electronic signature, or unique identifier.",
    "ITA_66D": "The account states cheating by personation using a computer resource or communication device.",
    "ITA_67": "The account states electronic publication or transmission of obscene, lascivious or prurient material without a depicted explicit act.",
    "ITA_67A": "The account states electronic publication or transmission of material containing a sexually explicit act or conduct.",
}


def main() -> None:
    assert len(POSITIVE) == 18 and all(len(patterns) == 5 for _, patterns in POSITIVE.values())
    assert len(UNCERTAIN) == 15 and len(OUT_OF_SCOPE) == 10
    with sqlite3.connect(DB_PATH) as conn:
        eligible = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT provision_id,verified_text,source_pdf_page FROM recommendable_provision")}
        assert set(POSITIVE) == set(eligible) - {"ITA_65"}
        assert all(pid in eligible for pid, *_ in UNCERTAIN)

    rows = []
    families = []
    for pid, (domain, patterns) in POSITIVE.items():
        for index, pattern in enumerate(patterns, 1):
            families.append((f"SYN_{pid}_{index:02d}", domain, pattern,
                             "provision_match", [pid] + (["BNS_319"] if pid == "ITA_66D" else []),
                             [], "", RATIONALES[pid]))
    for index, (pid, domain, pattern, missing) in enumerate(UNCERTAIN, 1):
        families.append((f"SYN_UNCERTAIN_{index:02d}", domain, pattern,
                         "insufficient_information", [], [pid], missing,
                         "The missing element prevents a positive section suggestion."))
    for index, (domain, pattern) in enumerate(OUT_OF_SCOPE, 1):
        families.append((f"SYN_OUT_{index:02d}", domain, pattern,
                         "out_of_scope", [], [], "",
                         "This reported matter is outside the current 19-section pilot scope."))

    for family_id, domain, pattern, outcome, positives, uncertain, missing, rationale in families:
        for actor_index, actor in enumerate(ACTORS[domain], 1):
            for context_index, frame in enumerate(REPORT_FRAMES, 1):
                sid = f"{family_id}_{actor_index:02d}{context_index:02d}"
                text = frame + pattern.format(actor=actor)
                assert len(text.split()) >= 20, sid
                assert not any(token in text.lower() for token in ("@", "aadhaar", "pan number")), sid
                rows.append({
                    "scenario_id": sid,
                    "scenario_group": family_id,
                    "language": "en",
                    "provenance_type": "synthetic",
                    "review_tier": "silver",
                    "family_id": family_id,
                    "family_pattern_sha256": hashlib.sha256(pattern.encode("utf-8")).hexdigest(),
                    "complaint_text": text,
                    "expected_outcome": outcome,
                    "possible_provision_ids": json.dumps(positives, separators=(",", ":")),
                    "uncertain_provision_ids": json.dumps(uncertain, separators=(",", ":")),
                    "missing_facts": missing,
                    "rationale": rationale,
                    "source_pages": json.dumps({p: eligible[p][1] for p in positives + uncertain}, sort_keys=True),
                    "variation_note": "Actor and reporting frame vary; legal fact pattern is shared within family.",
                })
    assert len(rows) == 2760 and len({r["complaint_text"] for r in rows}) == len(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter(r["expected_outcome"] for r in rows)
    print(json.dumps({"csv": str(OUT), "rows": len(rows), "fact_pattern_families": len(families),
                      "outcomes": dict(counts), "new_positive_section_families": len(POSITIVE),
                      "review_tier": "silver", "individual_row_legal_review_claimed": False}, indent=2))


if __name__ == "__main__":
    main()
