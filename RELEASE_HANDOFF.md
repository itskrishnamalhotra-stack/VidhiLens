# VidhiLens release handoff

## Live address

The citizen site is https://vidhilens-legal-ai-km.web.app and the separate reviewer sign-in is https://vidhilens-legal-ai-km.web.app/reviewer. Both are hosted in the existing Firebase project. The Firebase project ID and backend build ID still contain the former internal identifier because changing either would break existing authentication and notebook compatibility.

## Start a demo

1. Open `Krishna_Warm_Production_Benchmark.ipynb` from the active G or H `LegalAI` Drive folder in Google Colab, choose T4, and **Run all**. Approve Drive access. The notebook reuses the trained adapter, starts the model and backend, and publishes the temporary tunnel address to the Firebase runtime document.
2. Wait for `VIDHILENS IS READY` and the two site links. Keep Colab connected during the demonstration. The site reconnects automatically when the backend becomes available.
3. Sign in as a citizen at the main site or as the designated reviewer at `/reviewer`. Neither role needs to paste a tunnel URL or token. Each Drive copy has its own SQLite chat and case history; use one account at a time.

## Scope

The assistant offers research guidance and creates an internal review case after explicit user confirmation. It does not register an FIR or submit anything to a government authority. The model still requires a running Colab GPU or another GPU server; Firebase Hosting serves only the web app. The new name changed the UI, site address, report, and new case ID prefix; it did not retrain the model or change historical case IDs.
