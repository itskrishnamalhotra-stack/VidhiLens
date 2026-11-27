"""Synchronize the local VidhiLens master to the G/H Colab Drive folders.

Default is a read-only diff. --apply copies only changed managed files. Runtime
databases, credentials, notebook output and research archives are never pushed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


MASTER = Path(__file__).resolve().parents[1]
TARGETS = {
    "G": Path("G:/My Drive/LegalAI"),
    "H": Path("H:/My Drive/LegalAI"),
}
SKIP_DIRS = {"node_modules", "dist", ".firebase", ".playwright-cli", ".vite-temp", "__pycache__", ".git", "coverage"}
SKIP_FILES = {".env", ".env.local", ".env.production.local", "firebase-debug.log"}
NOTEBOOKS = ("Krishna_Warm_Production_Benchmark.ipynb", "Krishna_Train_Resume.ipynb")
EVIDENCE = (
    "training_results.json",
    "model_selection.json",
    "warm_vllm_report.json",
    "warm_vllm_predictions.json",
    "sealed_rag_benchmark_v1_report.json",
    "sealed_rag_benchmark_v1_predictions.json",
    "SEALED_BENCHMARK_V1_ERROR_ANALYSIS.json",
    "SEALED_BENCHMARK_V1_ERROR_ANALYSIS.md",
    "rag_v2_2_comparison_results.json",
)
DOCS = (
    "ACTIVE_DRIVE.md",
    "BACKEND_IMPLEMENTATION_STATUS.md",
    "RELEASE_HANDOFF.md",
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def notebook_sources(path: Path) -> list[tuple[str, str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return [(cell["cell_type"], "".join(cell.get("source", []))) for cell in document["cells"]]


def same_content(source: Path, target: Path) -> bool:
    if not target.is_file():
        return False
    if source.suffix == ".ipynb":
        return notebook_sources(source) == notebook_sources(target)
    return source.stat().st_size == target.stat().st_size and digest(source) == digest(target)


def stats(path: Path) -> list[int]:
    current = path.stat()
    return [current.st_size, current.st_mtime_ns]


def managed_files() -> dict[Path, Path]:
    files: dict[Path, Path] = {}

    def add(source: Path, relative: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(source)
        if relative in files:
            raise RuntimeError(f"Duplicate release path: {relative}")
        files[relative] = source

    for dirname in ("backend", "frontend", "evaluation"):
        base = MASTER / dirname
        for source in base.rglob("*"):
            if not source.is_file() or any(part in SKIP_DIRS for part in source.relative_to(base).parts):
                continue
            if source.name in SKIP_FILES or source.suffix in {".pyc", ".log"}:
                continue
            add(source, Path(dirname) / source.relative_to(base))

    for source in (MASTER / "model_artifacts" / "runs").rglob("*"):
        if source.is_file():
            add(source, Path("runs") / source.relative_to(MASTER / "model_artifacts" / "runs"))

    for name in NOTEBOOKS:
        add(MASTER / "colab" / name, Path(name))
    for name in ("colab_training_input_v5.zip", "rag_catalogue_v1.json"):
        add(MASTER / "exports" / name, Path(name))
    for name in EVIDENCE:
        add(MASTER / "release_evidence" / "H" / name, Path(name))
    for name in DOCS:
        add(MASTER / name, Path(name))
    for name in ("WARM_PRODUCTION_RUN.md",):
        add(MASTER / "colab" / name, Path(name))
    for source in (MASTER / "evaluation" / "sealed_rag_benchmark_v1").rglob("*"):
        if source.is_file():
            add(source, Path("sealed_rag_benchmark_v1") / source.relative_to(MASTER / "evaluation" / "sealed_rag_benchmark_v1"))
    return dict(sorted(files.items()))


def sync_one(label: str, files: dict[Path, Path], apply: bool) -> None:
    root = TARGETS[label]
    if root.resolve() != Path(f"{label}:/My Drive/LegalAI").resolve() or not root.is_dir():
        raise RuntimeError(f"Unexpected or unavailable Drive target: {root}")
    manifest_path = root / ".local_master_manifest.json"
    try:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        verified = previous.get("verified_stats", {})
    except (FileNotFoundError, json.JSONDecodeError):
        verified = {}
    changes: list[tuple[Path, Path]] = []
    for relative, source in files.items():
        target = root / relative
        cache_key = relative.as_posix()
        cached = verified.get(cache_key)
        stat_match = (target.is_file() and cached == [stats(source), stats(target)])
        if not stat_match and not same_content(source, target):
            changes.append((relative, source))
    print(f"{label}: {len(changes)} changed or missing of {len(files)} managed files")
    for relative, source in changes:
        print(f"  {'copy' if apply else 'would copy'} {relative}")
        if apply:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".syncing")
            shutil.copy2(source, temporary)
            if not same_content(source, temporary):
                temporary.unlink(missing_ok=True)
                raise RuntimeError(f"Copy verification failed: {target}")
            temporary.replace(target)
            if not same_content(source, target):
                raise RuntimeError(f"Target verification failed: {target}")
    if apply:
        manifest = {
            "schema_version": 2,
            "source": str(MASTER),
            "managed_files": [str(path).replace("\\", "/") for path in files],
            "runtime_data_excluded": ["app_data/", "tunnel_test_report.json"],
            "credentials_excluded": True,
            "verified_stats": {
                relative.as_posix(): [stats(source), stats(root / relative)]
                for relative, source in files.items()
            },
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{label}: managed files verified; live app_data and credentials untouched")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", nargs="+", choices=sorted(TARGETS), default=["G", "H"])
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    files = managed_files()
    for label in arguments.targets:
        sync_one(label, files, arguments.apply)


if __name__ == "__main__":
    main()
