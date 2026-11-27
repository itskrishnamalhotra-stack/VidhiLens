"""Preserve Drive-only LegalAI artifacts in the local phase1 master.

This command only reads G/H Drive and writes under the local project. It never
copies the separate Firebase credential folder or changes either live Drive.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PHASE1 = Path(__file__).resolve().parents[1]
DRIVES = {
    "G": Path("G:/My Drive/LegalAI"),
    "H": Path("H:/My Drive/LegalAI"),
}
CURRENT_NOTEBOOKS = {
    "Krishna_Warm_Production_Benchmark.ipynb",
    "Krishna_Train_Resume.ipynb",
}


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def copy_verified(source: Path, target: Path) -> bool:
    if target.is_file() and source.stat().st_size == target.stat().st_size:
        if digest(source) == digest(target):
            return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".copying")
    shutil.copy2(source, temporary)
    if digest(source) != digest(temporary):
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Copy verification failed: {source}")
    temporary.replace(target)
    return True


def snapshot_database(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    snapshot = sqlite3.connect(target)
    try:
        connection.backup(snapshot)
        result = snapshot.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite snapshot failed integrity check: {target}")
    finally:
        snapshot.close()
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Copy and verify files")
    args = parser.parse_args()
    for label, root in DRIVES.items():
        if not root.is_dir():
            raise FileNotFoundError(root)
        print(f"{label}: {root}")
        for notebook in root.glob("Krishna_*.ipynb"):
            if notebook.name not in CURRENT_NOTEBOOKS:
                target = PHASE1 / "archive" / "drive_notebooks" / label / notebook.name
                if args.apply:
                    copy_verified(notebook, target)
                print(f"  archive notebook: {notebook.name}")
        for evidence in root.iterdir():
            if evidence.is_file() and evidence.suffix.lower() in {".json", ".md"}:
                target = PHASE1 / "release_evidence" / label / evidence.name
                if args.apply:
                    copy_verified(evidence, target)
        source_db = root / "app_data" / "legalai.sqlite"
        if source_db.is_file():
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            target_db = PHASE1 / "runtime_backups" / label / f"legalai-{timestamp}.sqlite"
            if args.apply:
                snapshot_database(source_db, target_db)
            print(f"  preserve live database: {target_db}")
    runs = DRIVES["H"] / "runs"
    for source in runs.rglob("*"):
        if source.is_file():
            target = PHASE1 / "model_artifacts" / "runs" / source.relative_to(runs)
            if args.apply:
                copy_verified(source, target)
            print(f"  preserve trained artifact: {source.relative_to(runs)}")
    print("Local master import complete." if args.apply else "Dry run only; use --apply to import.")


if __name__ == "__main__":
    main()
