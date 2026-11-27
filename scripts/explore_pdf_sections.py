"""Report section-like headings from the actual Act text, excluding the contents."""

import re
from collections import Counter
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("BNS", ROOT / "sources" / "bns_2023_indiacode_2025-10-06.pdf", 15),
    ("ITA", ROOT / "sources" / "it_act_2000_indiacode.pdf", 4),
]
PATTERN = re.compile(r"^(?:\d+\[)?(?P<num>\d{1,3}[A-Z]?)\.\s+(?P<rest>.+)")

for label, path, start_page in SOURCES:
    doc = fitz.open(path)
    candidates = []
    for index in range(start_page, len(doc)):
        lines = doc[index].get_text().splitlines()
        for line in lines:
            match = PATTERN.match(line.strip())
            if match and (".—" in line or ".–" in line or "[Omitted" in line):
                candidates.append((match["num"], index + 1, line.strip()[:100]))
    counts = Counter(number for number, _, _ in candidates)
    print(label, "candidate_headings", len(candidates), "unique", len(counts))
    print("first", candidates[:8])
    print("last", candidates[-8:])
    print("duplicates", [(n, c) for n, c in counts.items() if c > 1][:20])
    if label == "BNS":
        missing = [number for number in range(1, 359) if str(number) not in counts]
        print("missing_1_to_358", missing)
