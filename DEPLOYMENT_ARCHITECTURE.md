# Portable demo and university deployment plan

Decision date: 16 September 2026. Owner: Krishna Malhotra. This is a Phase 1 design contract; no backend or Firebase project has been deployed.

## What the user will see

1. A Firebase Hosted web app with sign-in, a chat list, a new chat button, and separate histories for each chat.
2. In a chat, the user describes an incident. The assistant asks useful follow-up questions with options, `Other`, and `Not sure`, then shows possible **reviewed** BNS/IT Act sections with official source links or explains uncertainty.
3. If an in-scope provision is supportable, the assistant can offer to prepare a complaint **draft**. The user can inspect, edit, cancel, or explicitly confirm local saving. The app never claims that this files an FIR or sends a report to police.
4. Each saved draft has a private internal reference, version history, and delete/export controls. Another signed-in user cannot read it.

## One backend, three environments

The application API and model package have one container/configuration contract. They do not depend on a particular host path or notebook state. The frontend discovers the active backend through a small deployment configuration and uses HTTPS for API calls.

| Environment | Role | Practical decision |
| --- | --- | --- |
| Google Colab | All training and checkpoint/resume tests | A separate private training notebook; private Drive storage holds checkpoints and run manifests. No user complaint data in training. |
| Google Colab | Emergency, short interactive demo | A separate inference notebook may demonstrate the backend for a small controlled audience while the notebook is active. Its temporary endpoint is not a promised public or multi-user service. Do not embed credentials or private complaints in the notebook. |
| Short-lived cloud container/VM | Default final demo if university server is unavailable | Run the same API/model package with HTTPS, monitored cost, a fixed spend limit/instance cap, and a tested multi-user queue. Firebase Hosting serves the frontend. |
| University server | Long-term academic host after demo | Run the same API/model package behind HTTPS; configure model size and worker count to the available machine. |

Google's [Colab FAQ](https://research.google.com/colaboratory/faq.html) says managed runtimes prioritize interactive notebook use, limits vary, and unrelated web-service offerings are restricted. The [Colab terms](https://research.google.com/colaboratory/tos_v5.html) also restrict giving third parties access to Colab. A Colab endpoint may be useful for Krishna's live notebook demonstration, but the reliable multi-user path is a server or cloud host. This distinction is a deployment constraint, not a demand for computer specifications now. Hardware details are only needed when choosing final quantization, worker count, and measured latency for a specific university machine.

## Component contract

**Concrete implementation choice:** a Python **FastAPI** application is the backend. It exposes stable JSON endpoints such as `/health`, `/sessions`, `/sessions/{id}/messages`, `/analyze`, and `/drafts/{id}/confirm`. The code handles Firebase token verification, user/session authorization, law retrieval from the read-only SQLite snapshot, action validation, and saved-draft version checks. A separate local model-serving process supplies text generation; the Python API can call a quantized `llama.cpp` server on the same host or another compatible inference endpoint. The frontend is JavaScript/TypeScript on Firebase Hosting. “Same API” means the frontend sends the same request format and receives the same response format whether this Python service runs on a cloud VM or university server. Host-specific settings are configuration, not rewritten product logic. [Qwen's GGUF card](https://huggingface.co/Qwen/Qwen3-4B-GGUF) documents a `llama.cpp` server option; [llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) supports parallel slots and continuous batching.

```text
Firebase Hosting web app
  -> Firebase Authentication (one UID per user)
  -> Firestore (private users/{uid}/sessions/{sessionId}/... records)
  -> HTTPS API: same routes on cloud or university host
       -> verified Firebase identity and ownership checks
       -> bounded request queue + retrieval/model worker(s)
       -> reviewed SQLite law snapshot and provision allowlist
       -> session/draft store, versioned writes, audit metadata
```

The backend is stateless with respect to chat history: it reads/writes the session store for each request. A restart or second worker must not merge users' conversations. Store only a recent context window plus an explicit, versioned session summary for inference; retain full history separately for the user. Never let the client choose another UID, and derive all owner paths from the verified token. The law database and model weights are versioned read-only artifacts in the running service.

Firebase ID tokens travel to the backend over HTTPS and are verified before an API request is accepted. [Firebase documents this flow](https://firebase.google.com/docs/auth/admin/verify-id-tokens). For a portable demo without a service-account key inside Colab, the backend can use the user's token to access [Firestore REST under Security Rules](https://firebase.google.com/docs/firestore/use-rest-api). A production server can use managed credentials, but server SDK/service-account access bypasses Firestore Rules; the backend must then enforce UID ownership itself. Test both modes with two separate accounts. Firebase App Check, rate limits, and budget alerts add abuse protection but do not replace identity checks.

The web app uses a trusted deployment configuration for its API origin. Switching hosts changes the API URL, CORS allowlist, health check, and TLS certificate; it does not change the conversation or legal decision code. A temporary Colab tunnel URL is accepted only during a supervised demo, never silently left in a public configuration.

## Session and record shape

| Record | Minimum fields |
| --- | --- |
| `users/{uid}/sessions/{sessionId}` | `ownerUid`, title, created/updated time, status, model version, KB version, last message time |
| `.../messages/{messageId}` | role, text or structured option selection, timestamp, turn ID, `sessionId`; no access from another UID |
| `.../facts/{factId}` | field/value/state, source turn, correction history; a selected option is user-reported, not proven evidence |
| `.../drafts/{draftId}` | original narrative, structured draft, version, status, confirmed version/time, internal reference, change history |

Use opaque random IDs. Enforce per-user Rules on all client-readable records; deny by default. Prefer backend-owned writes for analysis, draft confirmation, and saved-record integrity. For the credential-free Colab mode, restrict client/REST writes with Rules and validate confirmation again in the API; do not claim that Rules alone prove an AI/legal result. Keep model outputs marked as such and hydrate statute text from the reviewed database only.

## Simultaneous users and cost

The API accepts overlapping HTTP requests and keeps each user's session isolated. A single GPU may still generate one response at a time: use a bounded FIFO queue, per-user request limits, timeout/cancel behavior, and clear `queued`/`working` UI states. Never silently drop or swap replies. Scale workers only if a measured load test shows need. Verify with at least five signed-in simulated users, several chats per user, concurrent turns, service restart, and cross-user access attempts. Record p50/p95 latency and failure/queue counts on the actual host.

Start with lexical retrieval and a small quantized open model only after the baseline is measured. Set max output tokens, context limits, model worker count, storage retention, cloud budget alerts, and instance caps before the cloud demo. Training runs in Colab; inference hosting is separately costed.

## Suggested host specifications for the first release

These are **engineering estimates**, not measured requirements. The current candidate is a 4B-parameter Qwen model. Its official Q4 GGUF weights are about **2.5 GB**, but inference also needs memory for the context/KV cache, concurrent users, runtime and operating system. [Qwen model card and files](https://huggingface.co/Qwen/Qwen3-4B-GGUF/tree/main). Keep chat context bounded and measure actual peak memory and latency before declaring a host sufficient.

| Use | CPU | RAM | GPU | Storage | Expected role |
| --- | --- | --- | --- | --- | --- |
| Retrieval-only baseline | 2–4 vCPU | 8 GB | None | 20+ GB SSD | Law search, sign-in and session flows; many concurrent lightweight requests |
| Minimum single-model demo | 4–8 vCPU | 16 GB | About 12 GB VRAM preferred | 50+ GB SSD | Quantized 4B inference with a short queue; measure latency |
| **Recommended university/cloud demo** | **8 vCPU** | **32 GB** | **16 GB VRAM** | **100 GB SSD** | One 4B model worker, several live users, bounded generation queue |
| More comfortable simultaneous generation | 8–16 vCPU | 32–64 GB | 24 GB VRAM | 100+ GB SSD | More parallel slots or longer contexts after load testing |

An 8 GB GPU or CPU-only 32 GB RAM machine may run a quantized 4B model, but response times and the number of active generations may be poor. If the university has a smaller machine, keep the same app and use the retrieval mode or a smaller model. If it has no GPU and the full model is needed for the final demo, rent a GPU host only for the presentation period. Prefer Linux for deployment and containerize the Python API and model runner. The **training** machine remains Google Colab and is a separate decision.

## Privacy and release gates

- Use fictional examples for class demo and testing. If real reports are later accepted, publish a consent/retention/delete policy before collection and get the relevant institutional/legal review.
- No chat text, access token, or draft body in request logs, analytics, crash traces, public Git, or Colab outputs. Keep secrets in managed configuration; avoid downloadable service-account JSON in notebooks.
- Test Firestore Rules in an emulator with user A, user B, and unauthenticated access. Test backend token expiry, wrong UID, repeated confirm, stale draft version, and duplicate requests.
- A final release needs source/status recheck, legal label review, measured unseen-case results, and a clear statement that saved drafts are not official filings.

## Build order

1. Finish the reviewed scenario pilot and sealed-test design while building the retrieval API.
2. Implement Firebase sign-in, private session storage, and chat history against the retrieval baseline.
3. Implement guided questions, source-backed results, draft/edit/cancel/confirm, and integrity checks.
4. Run the Colab training smoke/resume test, then the reviewed-data adapter experiment.
5. Connect the measured model, load-test concurrent sessions, and deploy the same backend package to the selected demo host.
6. Recheck sources, freeze results, and write the paper from saved runs.
