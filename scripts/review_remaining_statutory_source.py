"""Record conservative AI review of the 1,338 held statutory-triage prompts.

Every prompt was read in source order. Only rows whose reported facts support a
specific, source-checked BNS provision enter positive SFT. The rest become an
unlabelled challenge bank. Publisher outputs are never copied into targets.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "external_candidates" / "statutory_triage_bns_ipc_dataset_final_dense.jsonl"
AUDIT = ROOT / "review_automation" / "complaint_pool_v2"
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = AUDIT / "remaining_1338_review"
SYSTEM = ("Read the reported incident. Return JSON only with outcome, possible_provision_ids, "
          "and uncertain_sections. A section is only a possibility, never a finding of guilt. "
          "Never invent missing facts.")

# Explicit positive decisions from reading all 1,338 prompts against the
# operative text. IDs are source line numbers, not synthetic case identifiers.
# They target a whole provision. Publisher subsection labels are not endorsed.
GROUPS = {
    "BNS_64": "857 858 1754 1755 1759",
    "BNS_65": "1317 1397 1760 1761 1780",
    "BNS_67": "862 1098 1318",
    "BNS_70": "866 1401 1770 1771 1789 1790",
    "BNS_72": "1793",
    "BNS_82": "1025 1328 1329 1410 1807",
    "BNS_83": "1028",
    "BNS_87": "839 1812",
    "BNS_89": "750 1112 1332 1415 1816",
    "BNS_94": "758 1824",
    "BNS_97": "1117",
    "BNS_98": "55",
    "BNS_99": "1834",
    "BNS_106": "1859 1860",
    "BNS_109": "1863",
    "BNS_120": "772 774 1433",
    "BNS_115": "1617",
    "BNS_143": "1935",
    "BNS_126": "787 788",
    "BNS_131": "207 1922",
    "BNS_132": "1917",
    "BNS_139": "1139",
    "BNS_140": "834 836 1932 1933",
    "BNS_146": "1454 1455",
    "BNS_164": "305",
    "BNS_178": "630 633 1017 1169 1472 1491 1989 1990",
    "BNS_179": "643 1167 1987",
    "BNS_183": "1492 1992",
    "BNS_184": "669 670 671 1493 1993",
    "BNS_191": "272 470",
    "BNS_201": "345 493 2032",
    "BNS_204": "349 350 1507 2036",
    "BNS_208": "375 519 1184 2043",
    "BNS_209": "1511",
    "BNS_217": "532 1190 1516 1707 2058",
    "BNS_220": "535",
    "BNS_225": "1523",
    "BNS_226": "2074",
    "BNS_229": "546 547 552 554 2076 2085 2086 2095",
    "BNS_232": "76 1529 2089 2090",
    "BNS_241": "1535",
    "BNS_248": "584 2059 2116 2117",
    "BNS_253": "1543",
    "BNS_256": "601 1546 2128",
    "BNS_261": "1221",
    "BNS_262": "622 2139",
    "BNS_263": "617 1552",
    "BNS_266": "1553 2148 2149",
    "BNS_267": "624 1226",
    "BNS_269": "48 628 1228 2152 2153",
    "BNS_271": "679 680 1558 2156",
    "BNS_272": "1230 1559",
    "BNS_273": "681 2157",
    "BNS_279": "1235 2162",
    "BNS_280": "687 1236 2163",
    "BNS_281": "783",
    "BNS_282": "689 1238 2165",
    "BNS_283": "690",
    "BNS_285": "692 1240 1567",
    "BNS_286": "693 2168",
    "BNS_288": "696",
    "BNS_289": "2174",
    "BNS_290": "2176",
    "BNS_295": "70 2183",
    "BNS_297": "2185",
    "BNS_300": "1041 1574 2026",
    "BNS_301": "709 2192",
    "BNS_303": "148 291 390 445 568 915 2201",
    "BNS_305": "895 965",
    "BNS_306": "908 914 2204",
    "BNS_308": "880 1251 1273 2212 2213",
    "BNS_309": "876 877",
    "BNS_320": "929 930 1257",
    "BNS_326": "941 942 1584 1586",
    "BNS_328": "946 1341",
    "BNS_331": "954 955 1587",
    "BNS_336": "96 984 987 1258",
    "BNS_337": "1343",
    "BNS_340": "988 1344 1591",
    "BNS_341": "991 1594",
    "BNS_342": "996 1265 1346 1596",
    "BNS_352": "1040",
    "BNS_353": "1179",
    "BNS_354": "1046 1603",
    "BNS_355": "1048 1049 1276 1354 1604",
}

# A second look found these accounts repeated an earlier selected account with
# only a surface wording change. Keep the later wording for challenge analysis.
NEAR_DUPLICATE_HOLD = {628, 2128, 680, 1433, 877, 1273, 1491, 1559, 1992, 2058, 1257}

# Short accounts for which a plausible provision cannot be safely asserted.
# These teach a specific missing-fact question rather than the publisher label.
CLARIFY = {
    1: ("BNS_287", "whether the fire resulted from negligent handling and endangered human life or safety"),
    2: ("BNS_115", "whether the blow caused bodily pain or injury and was intentional"),
    4: ("BNS_356", "the exact imputation published to others and whether it harmed reputation"),
    12: ("BNS_300", "whether a lawful religious worship assembly was actually disturbed"),
    31: ("BNS_356", "whether the cartoon was published to others and presented a reputation-harming imputation"),
    72: ("BNS_297", "whether the lottery was a State lottery or authorised by the State Government"),
    73: ("BNS_89", "whether the person voluntarily caused the miscarriage without the pregnant woman's consent"),
    376: ("BNS_210", "whether the person was legally bound to produce the document to that public servant"),
    513: ("BNS_177", "whether election law required this person to keep campaign expense accounts"),
    520: ("BNS_210", "whether the person was legally bound to produce the document and intentionally omitted it"),
    521: ("BNS_210", "whether a lawful court order legally required production of that document"),
    573: ("BNS_241", "whether the document could be lawfully compelled as evidence and was destroyed to prevent production"),
    740: ("BNS_93", "whether the person was a parent or had care of the newborn when it was abandoned"),
    150: ("BNS_351", "the threat's exact words, intended effect, and whether it caused alarm"),
    511: ("BNS_176", "whether the payment was an election expense made without the candidate's written authority"),
    284: ("BNS_191", "whether a group of at least five shared an unlawful common object and used force"),
    316: ("BNS_189", "the group's size and common object, beyond merely protesting"),
    331: ("BNS_193", "whether the landholder knew of the riot and failed to prevent or report it as required"),
    523: ("BNS_211", "whether the person had a specific legal duty to report the crime"),
    591: ("BNS_251", "whether the offered payment was to conceal a non-compoundable offence from punishment"),
    634: ("BNS_180", "whether the person knew the coins were counterfeit and intended to use them as genuine"),
    674: ("BNS_179", "whether the seller knew the stamps were counterfeit and passed them as genuine"),
    700: ("BNS_293", "whether there was a lawful injunction ordering the public nuisance to stop"),
    701: ("BNS_294", "the material's contents and whether it meets the statutory obscenity test and no exception applies"),
    711: ("BNS_302", "whether the words were uttered with a deliberate intent to wound religious feelings"),
    745: ("BNS_89", "whether anyone voluntarily caused the miscarriage without the pregnant woman's consent"),
    792: ("BNS_258", "whether the holder had legal confinement authority and knowingly acted contrary to the release order"),
    832: ("BNS_139", "whether the child was kidnapped or maimed for begging"),
    849: ("BNS_99", "whether a child was actually bought or obtained with the prohibited purpose"),
    1239: ("BNS_284", "whether the overloaded vessel was carrying passengers for hire and was unsafe"),
    861: ("BNS_66", "whether injuries inflicted during the rape caused a persistent vegetative state"),
    874: ("BNS_303", "whether the dog was taken dishonestly out of the owner's possession without consent"),
    918: ("BNS_317", "whether the goods were stolen and the buyer knew or had reason to believe this"),
    940: ("BNS_325", "whether the animal was killed or maimed by the poisoning"),
    1002: ("BNS_343", "whether anyone fraudulently destroyed or concealed the will"),
    1033: ("BNS_356", "what was posted and why it would harm the person's reputation"),
    1101: ("BNS_72", "whether the shared details identify a protected sexual-offence victim"),
    1484: ("BNS_179", "whether the person knew the note was counterfeit and passed it as genuine"),
    1564: ("BNS_278", "whether the seller knowingly supplied one drug or preparation as a different one"),
    1566: ("BNS_284", "whether the vessel was conveying people for hire and was unsafe when boarded"),
    1813: ("BNS_87", "whether the woman was abducted or induced to go for forced marriage or illicit intercourse"),
    1985: ("BNS_176", "whether the expense lacked the candidate's written authority and was not lawfully ratified"),
    1164: ("BNS_175", "whether the known-false statement concerned a candidate's personal character or conduct"),
    1249: ("BNS_298", "whether the temple was defiled with intent or knowledge of insulting a religion"),
    1500: ("BNS_189", "whether at least five people shared one of the statutory unlawful common objects"),
    1556: ("BNS_271", "whether the disease was dangerous to life and the conduct was negligent or intentional"),
    1570: ("BNS_294", "what the book contains and whether a statutory exception applies"),
    1609: ("BNS_347", "whether an ownership property mark was counterfeited, rather than only a product design"),
    2013: ("BNS_193", "whether the landholder knew of the riot and failed to prevent or report it as required"),
    2051: ("BNS_217", "whether the false statement was intended to misuse a public servant's power to injure another"),
    2169: ("BNS_287", "whether the fire resulted from negligent handling that endangered human life or safety"),
    2175: ("BNS_290", "what negligent construction or safety omission caused the collapse and endangered people"),
    2188: ("BNS_299", "whether the content deliberately and maliciously insulted religion to outrage a class's feelings"),
    2200: ("BNS_303", "whether taking the book was dishonest rather than an authorised temporary borrowing"),
}


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def norm(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.casefold()))


def main() -> None:
    selected: dict[int, str] = {}
    for pid, numbers in GROUPS.items():
        for number in map(int, numbers.split()):
            if number in selected:
                raise ValueError(f"Duplicate decision for row {number}")
            selected[number] = pid
    prior_review = OUT / "decisions.csv"
    if prior_review.exists():
        scope = {int(r["source_row"]): {"input_sha256": r["input_sha256"],
                                        "source_label": r["publisher_label"]}
                 for r in csv.DictReader(prior_review.open(encoding="utf-8", newline=""))}
    else:
        scope = {int(r["row_number"]): r for r in csv.DictReader(
            (AUDIT / "final_training_dispositions.csv").open(encoding="utf-8", newline=""))
            if r["source"] == "statutory_triage" and
            (r["decision"] == "excluded_source_mapping_quality" or
             r["basis"] == "AI_batch_fact_to_law_review")}
    if len(scope) != 1338 or not set(selected) <= set(scope):
        raise ValueError("Review scope changed or selected row outside scope")
    if set(CLARIFY) & set(selected) or not set(CLARIFY) <= set(scope):
        raise ValueError("Clarification scope overlaps positives or lies outside queue")
    source = {n: json.loads(line) for n, line in enumerate(SOURCE.open(encoding="utf-8"), 1)
              if n in scope}
    if set(source) != set(scope):
        raise ValueError("Source lines missing")
    with sqlite3.connect(DB) as conn:
        law = {pid: (status, kind, body, page) for pid, status, kind, body, page in conn.execute(
            "SELECT provision_id,legal_status,provision_kind,verified_text,source_pdf_page FROM provision")}
        previous = {norm(t) for (t,) in conn.execute("SELECT complaint_text FROM scenario")}
    OUT.mkdir(parents=True, exist_ok=True)
    decisions, positives, clarifications, challenge = [], [], [], []
    for n, record in sorted(scope.items()):
        prompt = source[n]["instruction"].strip()
        if sha(prompt) != record["input_sha256"]:
            raise ValueError(f"Source hash mismatch: {n}")
        publisher_label = record["source_label"]
        original_pid = "BNS_" + re.match(r"\d+", publisher_label).group()
        if n in selected:
            pid = selected[n]
            status, kind, body, page = law[pid]
            if status != "in_force" or kind != "offence" or not body or not page:
                raise ValueError(f"Law not source-ready: {pid}")
            if norm(prompt) in previous or n in NEAR_DUPLICATE_HOLD:
                decision, reason = "duplicate_held", "Exact or near duplicate of an existing approved research case."
            else:
                previous.add(norm(prompt))
                target = {"outcome": "provision_match", "possible_provision_ids": [pid],
                          "uncertain_sections": []}
                positives.append({
                    "id": f"reviewed-source-{n}",
                    "messages": [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": prompt},
                                 {"role": "assistant", "content": json.dumps(target, separators=(",", ":"))}],
                    "metadata": {"kind": "triage", "split": "train", "source": "statutory_triage",
                                 "source_row": n, "input_sha256": sha(prompt),
                                 "publisher_label_untrusted": publisher_label,
                                 "reviewed_target": pid, "verified_text_sha256": sha(body),
                                 "source_pdf_page": page,
                                 "review_status": "AI_reviewed_source_grounded_research_case",
                                 "quality_limit": "Short prompt; evaluate against neighbouring provisions before release."}
                })
                decision = "positive_relabelled" if original_pid != pid else "positive_same_provision"
                reason = "Reported conduct supports this whole provision as a possibility; publisher output discarded."
        elif n in CLARIFY:
            pid, missing = CLARIFY[n]
            status, kind, body, page = law[pid]
            if status != "in_force" or kind != "offence" or not body or not page:
                raise ValueError(f"Clarification law not source-ready: {pid}")
            target = {"outcome": "insufficient_information", "possible_provision_ids": [],
                      "uncertain_sections": [{"provision_id": pid, "missing_facts": missing}]}
            clarifications.append({
                "id": f"reviewed-source-clarify-{n}",
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": prompt},
                             {"role": "assistant", "content": json.dumps(target, separators=(",", ":"))}],
                "metadata": {"kind": "triage", "split": "train", "source": "statutory_triage",
                             "source_row": n, "input_sha256": sha(prompt),
                             "publisher_label_untrusted": publisher_label,
                             "reviewed_target": pid, "verified_text_sha256": sha(body),
                             "source_pdf_page": page,
                             "review_status": "AI_reviewed_missing_fact_research_case"}
            })
            decision, reason = "clarification_train", missing
        else:
            pid = ""
            decision = "challenge_not_positive"
            reason = ("Reported facts do not securely establish the publisher's provision, are a legal/defence "
                      "question, or omit a material element. Retain as an unlabelled challenge; do not train the publisher answer.")
        decisions.append({"source_row": n, "decision": decision, "publisher_label": publisher_label,
                          "reviewed_target": pid, "reason": reason, "input_sha256": sha(prompt),
                          "input_text": prompt})
        if decision in ("challenge_not_positive", "duplicate_held"):
            challenge.append({"id": f"source-challenge-{n}", "input": prompt,
                              "metadata": {"source": "statutory_triage", "source_row": n,
                                           "input_sha256": sha(prompt),
                                           "publisher_label_untrusted": publisher_label,
                                           "review_decision": decision,
                                           "not_a_supervised_target": True}})
    with (OUT / "decisions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(decisions[0])); writer.writeheader(); writer.writerows(decisions)
    for name, rows in (("positive_train.jsonl", positives),
                       ("clarification_train.jsonl", clarifications),
                       ("unlabelled_challenges.jsonl", challenge)):
        with (OUT / name).open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    result = {"scope": len(scope), "decisions": dict(Counter(r["decision"] for r in decisions)),
              "positive_train": len(positives), "clarification_train": len(clarifications),
              "unlabelled_challenges": len(challenge),
              "warning": "Unlabelled challenges are useful for retrieval and error analysis, but cannot be scored or used as supervised targets until individually relabelled.",
              "positive_source_limit": "These short AI-reviewed examples are research candidates, not independent legal validation or release approval.",
              "file_sha256": {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in
                              ("decisions.csv", "positive_train.jsonl", "clarification_train.jsonl",
                               "unlabelled_challenges.jsonl")}}
    (OUT / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
