# VidhiLens

VidhiLens is a research prototype that helps a user describe an incident in ordinary language, identifies possible provisions of the Bharatiya Nyaya Sanhita and Information Technology Act, asks for missing facts, and prepares an editable internal complaint draft. A separate reviewer interface supports case review and follow-up. It does not file an FIR or submit a report to a government system.

## How it works

The backend combines a Qwen3 4B Instruct base model with a trained LoRA adapter for complaint triage. Retrieval supplies reviewed statutory text and provision metadata at inference time. The API checks returned provision identifiers against that catalogue before presenting results. The frontend is a React application; the API is built with FastAPI.

## Repository map

- `backend/` — FastAPI service, grounded analysis, case workflow, and tests.
- `frontend/` — citizen and reviewer React interfaces.
- `colab/` — training and demo notebooks plus their supporting code.
- `scripts/` — dataset preparation and research scripts.
- `evaluation/` — benchmark summaries and acceptance evidence.
- `schema.sql` and the project notes — data structure and development record.
- `docs/VidhiLens_Project_Report.pdf` — project report.

## Completed project artifacts

The repository includes the completed [master research database](db/master_dataset.sqlite), [frozen Colab training input](exports/colab_training_input_v5.zip), [RAG catalogue](exports/rag_catalogue_v1.json), and [selected LoRA adapter](model_artifacts/runs/complaint_only/final_adapter.zip). The database and adapter are stored with Git LFS. Clone with Git LFS installed or run `git lfs pull` after cloning to download their real contents.

The adapter is for `Qwen/Qwen3-4B-Instruct-2507` at revision `cdbee75f17c01a7cc42f958dc650907174af0554`. The base model is obtained from its model provider when the notebook runs. Downloaded source archives, older training variants, intermediate checkpoints, Firebase credentials, and live user case history are excluded.

## Run the application

See [backend/README.md](backend/README.md) for API setup and tests, [frontend/README.md](frontend/README.md) for the web interface, and [colab/README.md](colab/README.md) for the Colab workflow. Example environment files describe configuration fields without containing private credentials.

## Evaluation scope

The reported benchmark scores measure agreement with research labels on a limited test set. They are not a claim of perfect legal accuracy. A qualified reviewer should validate legal conclusions before any real-world use.

Project author: Krishna Malhotra (Enrolment No. 06816404526). Mentor: Prof. Anurag Jain.
