# Backend implementation status

Date: 27 September 2026

The first deployable backend is implemented in `phase1/backend` and copied to the active Google Drive project. It calls the same persistent vLLM base model and LoRA names as the validated warm benchmark and embeds an exact copy of the tested grounded RAG core.

Implemented:

- FastAPI service with health, direct analysis, session, message and complaint-draft routes.
- Multiple users and multiple sessions with owner-scoped SQLite records.
- Concurrent model requests through a bounded four-slot queue; same-session turns are serialized.
- Verified law text and source hydration from `rag_catalogue_v1.json`.
- Missing-fact questions and out-of-scope handling.
- Draft preview, precise edits, mandatory reanalysis after legally relevant edits, explicit local confirmation, cancellation and deletion.
- Firebase token verification mode for the later hosted frontend.
- Colab starter cell that connects the API to the already warm vLLM server.
- Container definition for the cloud or university-server API process.

Verification completed locally:

- The backend RAG core is byte-identical to the benchmarked RAG core.
- Grounded pipeline output uses a real reviewed catalogue entry and official source link.
- Cross-user session access is rejected.
- Draft versions reject stale edits or confirmation.
- Legally relevant draft edits cannot be confirmed before reanalysis.
- Local saved records can be deleted.

## External endpoint verification

The temporary HTTPS endpoint check completed on 27 September 2026. The evidence is saved at `evaluation/tunnel_test_report.json` and in Drive as `LegalAI/tunnel_test_report.json`.

- Secure API, database, LoRA and base model health: passed.
- Invalid access token rejected: passed.
- Cross-user session access rejected: passed.
- External complaint analysis returned BNS 303 for the theft smoke case: passed.
- Local complaint-draft save boundary: passed; no official filing was performed.
- Four simultaneous external requests: passed in 22.223 seconds wall time.
- Overall result: `all_checks_passed: true`.

The Quick Tunnel URL is temporary and lasts only while the Colab runtime and tunnel process remain active. Firebase authentication and the frontend are the next implementation stage.
