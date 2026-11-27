# VidhiLens local master and Drive copies

The editable source of truth is `E:\term paper project\phase1`. Develop and test here. Run `python scripts/sync_legalai_drives.py --targets H G` to preview differences, then add `--apply` to copy changed managed files to both `LegalAI` Drive folders.

- G deployment copy: `G:\My Drive\LegalAI`
- H deployment copy: `H:\My Drive\LegalAI`
- Colab path under either mounted account: `/content/drive/MyDrive/LegalAI`
- Private Firebase credential under each account: `MyDrive/NyayaSetu Credentials/firebase-colab-runtime.json`

The sync never copies private credentials or `app_data/legalai.sqlite`. Each Drive account has its own live cases and chat history. Database snapshots are preserved locally in `runtime_backups/G` and `runtime_backups/H`; they must be merged deliberately if a single shared history is needed. The notebooks in each Drive may have different execution outputs even when their code is identical.

Trained adapters and checkpoints are preserved in `model_artifacts/runs`. Research results are in `release_evidence`, and superseded notebook copies are in `archive/drive_notebooks`. See `LOCAL_MASTER.md` for the release layout and cleanup policy.
