# LegalAI backend

This FastAPI service wraps the Qwen LoRA plus grounded RAG pipeline. The base model handles ordinary chat and asks focused follow-up questions. For incident reports, LoRA triage and a source-grounded assessment identify possible BNS or IT Act provisions.

## Included product behavior

- Private users, multiple chat sessions, and persistent chat history.
- Model-driven ordinary conversation, with incident answers passed back into legal analysis.
- Source-backed BNS and IT Act results from the reviewed catalogue.
- Focused missing-fact questions with `Yes`, `No`, `Not sure`, and `Other` choices.
- Complaint draft preview, exact field edits, reanalysis after legally relevant edits, explicit confirmation, cancellation, and deletion.
- A saved draft receives an internal project reference. It is never described as an FIR or government submission.
- Internal cases preserve submitted reports and chats, accept evidence and messages, and have an audited reviewer decision history.
- Firebase users verify a phone number before sending an internal case. The private Colab demo token is bound to Krishna's demo account, and the reviewer uses a separate token.
- Per-session request locks, SQLite WAL mode, and draft version checks protect simultaneous requests.

## Run beside the warm Colab vLLM server

The warm notebook must first show that both `legalai-base` and `legal-complaint-lora` are ready. Then run `COLAB_API_CELL.py` as a notebook cell. It starts this API on port 8080 and performs one real smoke analysis through the already-loaded model. The supplied cell permits the VidhiLens Firebase Hosting origins and the previous site during transition.

The Colab starter creates a random demonstration access token for Krishna. Enter it in the frontend or send it as a bearer token:

```text
Authorization: Bearer <random token from /content/legal_ai_demo_token>
X-LegalAI-Demo-User: krishna
```

The notebook also creates a separate reviewer token. Keep both private. A demo token does not verify someone's real identity.

Use `LEGALAI_AUTH_MODE=firebase` and install `requirements-firebase.txt` before connecting a public frontend. In Firebase mode the API verifies ID tokens and derives the owner UID from the verified token.

## Local API test

From the `phase1` directory, with an OpenAI-compatible vLLM server on port 8000:

```powershell
$env:PYTHONPATH = "backend"
python -m pip install -r backend\requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --workers 1
```

Open `http://127.0.0.1:8080/docs` for the generated API explorer.

## Routes

| Route | Purpose |
| --- | --- |
| `GET /health?deep=true` | API, database, base model, and LoRA readiness |
| `POST /sessions` | Create a private chat |
| `GET /sessions` | List the signed-in user's chats |
| `GET /sessions/{id}` | Read one owned chat and its history |
| `DELETE /sessions/{id}` | Delete an unfinished chat or archive a submitted chat |
| `POST /sessions/{id}/messages` | Add facts and run the full legal pipeline |
| `POST /analyze` | Run a direct authenticated analysis |
| `POST /drafts` | Create an unconfirmed complaint draft from a positive analysis |
| `PATCH /drafts/{id}` | Apply precise, version-checked edits |
| `POST /drafts/{id}/reanalyze` | Recheck provisions after legally relevant edits |
| `POST /drafts/{id}/confirm` | Explicitly save the current local draft version |
| `POST /drafts/{id}/cancel` | Cancel an unconfirmed draft |
| `DELETE /drafts/{id}` | Delete a locally saved record |
| `GET /me`, `GET /drafts` | Read account capability and drafts |
| `POST /cases`, `GET /cases`, `GET /cases/{id}` | Submit, list, and inspect internal cases |
| `POST /cases/{id}/messages` | User and reviewer follow-up |
| `POST /cases/{id}/review-request` | Case owner asks to reopen a closed internal review with a reason |
| `POST /cases/{id}/evidence`, `GET /cases/{id}/evidence/{file}` | Attach and read JPG, PNG, or PDF evidence |
| `GET /review/cases`, `POST /review/cases/{id}/decision` | Reviewer queue and auditable decisions |

## Tests

The tests use a fake model server for API state tests and the real reviewed catalogue for grounded pipeline tests:

```powershell
$env:PYTHONPATH = "backend"
python -m unittest discover -s backend\tests -v
```

Build the API container from the `phase1` directory:

```powershell
docker build -f backend\Dockerfile -t legalai-api .
```

Run one API worker per shared SQLite database. vLLM handles model batching separately. For a later multi-instance deployment, move session and draft storage to PostgreSQL or Firestore while keeping these route contracts.
