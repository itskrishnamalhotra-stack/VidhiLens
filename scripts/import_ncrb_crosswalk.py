"""Pin NCRB's IPC/BNS correspondence as unapproved mapping candidates.

The official table is a useful lookup for legacy IPC labels, but a matching
row is never evidence that the two provisions have identical legal elements.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter

from bs4 import BeautifulSoup

from build_full_kb import DB_PATH, ROOT, sha256


IPC_HEAD = re.compile(r"^(\d{1,3}[A-Z]?)(?=\.|\s*\(|\s)")
BNS_HEAD = re.compile(r"^(\d{1,3})(?=\.|\s*\(|\s)")


def normalize(value: str) -> str:
    return " ".join(value.split())


def pairs(table, *, reverse: bool) -> dict[tuple[str, str], tuple[int, str, str]]:
    found = {}
    for number, row in enumerate(table.find_all("tr"), start=1):
        cells = row.find_all("td")
        if len(cells) != 2:
            continue
        first, second = (normalize(cell.get_text(" ", strip=True)) for cell in cells)
        if reverse:
            ipc = IPC_HEAD.match(first)
            bns = BNS_HEAD.match(second)
            ipc_text, bns_text = first, second
        else:
            bns = BNS_HEAD.match(first)
            ipc = IPC_HEAD.match(second)
            ipc_text, bns_text = second, first
        if not ipc or not bns:
            continue
        key = (ipc.group(1), "BNS_" + bns.group(1))
        found.setdefault(key, (number, ipc_text, bns_text))
    return found


def main() -> None:
    manifest = json.loads((ROOT / "ncrb_crosswalk_manifest.json").read_text(encoding="utf-8"))
    path = ROOT / manifest["local_path"]
    if sha256(path) != manifest["sha256"]:
        raise ValueError("NCRB table hash changed")
    soup = BeautifulSoup(path.read_text(encoding="utf-8-sig"), "html.parser")
    forward = soup.find("table", id="example")
    reverse = soup.find("table", id="exampleold")
    if not forward or not reverse:
        raise ValueError("NCRB table structure changed")
    forward_pairs = pairs(forward, reverse=False)
    reverse_pairs = pairs(reverse, reverse=True)
    reciprocal = sorted(forward_pairs.keys() & reverse_pairs.keys())
    if len(reciprocal) < 500:
        raise ValueError(f"Too few reciprocal IPC/BNS candidates: {len(reciprocal)}")
    ipc_degree = Counter(ipc for ipc, _ in reciprocal)
    bns_degree = Counter(bns for _, bns in reciprocal)
    expected = []
    for ipc, bns in reciprocal:
        reverse_row, ipc_text, bns_text = reverse_pairs[(ipc, bns)]
        forward_row = forward_pairs[(ipc, bns)][0]
        expected.append((ipc, bns, reverse_row, forward_row, ipc_text, bns_text,
                         int("(Change)" in bns_text), manifest["sha256"], 0))
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("""CREATE TABLE IF NOT EXISTS ipc_bns_crosswalk_candidate (
            ipc_section TEXT NOT NULL,
            bns_provision_id TEXT NOT NULL REFERENCES provision(provision_id),
            reverse_table_row INTEGER NOT NULL,
            forward_table_row INTEGER NOT NULL,
            ipc_description TEXT NOT NULL,
            bns_description TEXT NOT NULL,
            change_marker INTEGER NOT NULL CHECK (change_marker IN (0,1)),
            source_sha256 TEXT NOT NULL,
            training_label_approved INTEGER NOT NULL DEFAULT 0
                CHECK (training_label_approved=0),
            PRIMARY KEY (ipc_section,bns_provision_id)
        )""")
        prior = conn.execute("""SELECT ipc_section,bns_provision_id,reverse_table_row,
            forward_table_row,ipc_description,bns_description,change_marker,
            source_sha256,training_label_approved FROM ipc_bns_crosswalk_candidate
            ORDER BY ipc_section,bns_provision_id""").fetchall()
        if prior and prior != expected:
            raise ValueError("Existing crosswalk differs; create a versioned migration")
        if not prior:
            conn.executemany("INSERT INTO ipc_bns_crosswalk_candidate VALUES (?,?,?,?,?,?,?,?,?)", expected)
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Crosswalk foreign key failure")
        conn.commit()
    report = {"source_url": manifest["url"], "source_sha256": manifest["sha256"],
              "forward_pairs_parsed": len(forward_pairs),
              "reverse_pairs_parsed": len(reverse_pairs),
              "reciprocal_candidate_pairs": len(reciprocal),
              "unique_ipc_sections": len(ipc_degree),
              "unique_bns_sections": len(bns_degree),
              "ipc_sections_with_multiple_bns_candidates": sum(v > 1 for v in ipc_degree.values()),
              "bns_sections_with_multiple_ipc_candidates": sum(v > 1 for v in bns_degree.values()),
              "pairs_marked_changed": sum(row[6] for row in expected),
              "training_labels_approved": 0,
              "note": "NCRB correspondence is only a candidate lookup. Compare offence elements and facts before relabelling any IPC complaint as BNS."}
    out = ROOT / "ncrb_crosswalk_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
