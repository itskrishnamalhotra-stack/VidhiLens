# VidhiLens local master

**Edit this folder, not the Google Drive copies:** `E:\term paper project\phase1`.

## What is authoritative

| Local location | Purpose | Drive location |
| --- | --- | --- |
| `backend/` | API, legal workflow, Colab startup cells, tests | `LegalAI/backend/` |
| `frontend/` | Firebase website source and tests | `LegalAI/frontend/` (source only) |
| `colab/Krishna_Warm_Production_Benchmark.ipynb` | Current one-click demo notebook | `LegalAI/` |
| `colab/Krishna_Train_Resume.ipynb` | Training and batch-test notebook | `LegalAI/` |
| `exports/colab_training_input_v5.zip` | Training input | `LegalAI/` |
| `exports/rag_catalogue_v1.json` | Verified retrieval catalogue | `LegalAI/` |
| `model_artifacts/runs/` | Trained adapters and resumable checkpoints | `LegalAI/runs/` |
| `evaluation/` and `release_evidence/H/` | Benchmark inputs, reports, predictions | Selected files in `LegalAI/` |

Historical notebooks from both accounts are retained in `archive/drive_notebooks/`. The local research notebook series is in `archive/research_notebooks/`. These are not part of the live Colab folder. G and H case databases are backed up independently in `runtime_backups/`.

## Update both Drive copies

1. Edit and test files in this local folder.
2. Preview: `python scripts/sync_legalai_drives.py --targets H G`
3. Apply: `python scripts/sync_legalai_drives.py --targets H G --apply`
4. Confirm the final output says zero changed managed files on a new preview.

The script compares contents and copies only changed managed files. It never copies `NyayaSetu Credentials`, SQLite case data, frontend build cache, Python cache, or notebook output from the local copy. Keep `app_data/` separate: switching between G and H still means switching case histories until a shared production database is implemented.

Run `python scripts/prepare_local_master.py --apply` only when importing newly produced Drive model artifacts, benchmark evidence, or a fresh database snapshot back into the local master. It does not change Drive files.
