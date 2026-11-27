"""Copy this cell into the warm vLLM notebook after the server is ready."""

import json
import os
import subprocess
import sys
import time
import urllib.request
import socket
from pathlib import Path

PROJECT = Path("/content/drive/MyDrive/LegalAI")
BACKEND = PROJECT / "backend"
CATALOGUE = PROJECT / "rag_catalogue_v1.json"

if not (BACKEND / "app" / "main.py").is_file():
    raise FileNotFoundError(f"Backend files are missing: {BACKEND}")
if not CATALOGUE.is_file():
    raise FileNotFoundError(f"RAG catalogue is missing: {CATALOGUE}")

subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q", "-r", str(BACKEND / "requirements-firebase.txt")
])

os.environ["GOOGLE_CLOUD_PROJECT"] = "nyayasetu-legal-ai-km"
SERVICE_ACCOUNT_FILE = Path("/content/drive/MyDrive/NyayaSetu Credentials/firebase-colab-runtime.json")
if SERVICE_ACCOUNT_FILE.is_file():
    key = json.loads(SERVICE_ACCOUNT_FILE.read_text(encoding="utf-8"))
    if (key.get("type") != "service_account"
            or key.get("project_id") != "nyayasetu-legal-ai-km"
            or key.get("client_email") !=
            "nyayasetu-colab-runtime@nyayasetu-legal-ai-km.iam.gserviceaccount.com"):
        raise RuntimeError("The private Drive credential is not the dedicated VidhiLens Colab account")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(SERVICE_ACCOUNT_FILE)
    os.environ.pop("GOOGLE_CLOUD_QUOTA_PROJECT", None)
    print("Using the dedicated VidhiLens credential from the private Drive folder.")
else:
    from google.colab import auth as colab_auth
    colab_auth.authenticate_user()
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    os.environ["GOOGLE_CLOUD_QUOTA_PROJECT"] = "nyayasetu-legal-ai-km"
    print("No private Drive credential found; using this Colab account's Google access.")
import google.auth
google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials as firebase_credentials
try:
    firebase_admin.delete_app(firebase_admin.get_app())
except ValueError:
    pass
firebase_admin.initialize_app(
    credential=(firebase_credentials.Certificate(str(SERVICE_ACCOUNT_FILE))
                if SERVICE_ACCOUNT_FILE.is_file()
                else firebase_credentials.ApplicationDefault()),
    options={"projectId": "nyayasetu-legal-ai-km"},
)
try:
    next(iter(firebase_auth.list_users(max_results=1).iterate_all()), None)
except Exception as error:
    raise RuntimeError(
        "The available credential cannot read Firebase Authentication users "
        f"({type(error).__name__}). The dedicated key belongs at "
        f"{SERVICE_ACCOUNT_FILE}; alternatively, the Colab account needs project access."
    ) from error

EXPECTED_API_BUILD = "nyayasetu_draft_intake_2026_09_29"

def legalai_ready(root):
    try:
        with urllib.request.urlopen(root + "/health", timeout=2) as response:
            body = json.loads(response.read())
            return (response.status == 200 and body.get("api") == "ready"
                    and body.get("build_id") == EXPECTED_API_BUILD
                    and body.get("auth_mode") == "firebase")
    except Exception:
        return False

def port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0

# Reuse any healthy LegalAI API. Otherwise choose a free port without stopping
# or interfering with another notebook service.
API_PORT = None
for candidate in range(8080, 8091):
    candidate_root = f"http://127.0.0.1:{candidate}"
    if legalai_ready(candidate_root):
        API_PORT = candidate
        break
if API_PORT is None:
    API_PORT = next((candidate for candidate in range(8080, 8091) if port_is_free(candidate)), None)
if API_PORT is None:
    raise RuntimeError("No free API port was found between 8080 and 8090")

API_ROOT = f"http://127.0.0.1:{API_PORT}"
API_LOG = Path(f"/content/legal_ai_api_{API_PORT}.log")

if legalai_ready(API_ROOT):
    print("Reusing healthy LegalAI API:", API_ROOT)
else:
    environment = os.environ.copy()
    environment.update({
        "PYTHONPATH": str(BACKEND),
        "LEGALAI_PROJECT_ROOT": str(PROJECT),
        "LEGALAI_DATABASE_PATH": str(PROJECT / "app_data" / "legalai.sqlite"),
        "LEGALAI_CATALOGUE_PATH": str(CATALOGUE),
        "LEGALAI_AUTH_MODE": "firebase",
        "FIREBASE_PROJECT_ID": "nyayasetu-legal-ai-km",
        "GOOGLE_CLOUD_PROJECT": "nyayasetu-legal-ai-km",
        "LEGALAI_REVIEWER_EMAILS": "its.krishnamalhotra@gmail.com",
        "LEGALAI_CORS_ORIGINS": (
            "https://vidhilens-legal-ai-km.web.app,"
            "https://vidhilens-legal-ai-km.firebaseapp.com,"
            "https://nyayasetu-legal-ai-km.web.app,"
            "https://nyayasetu-legal-ai-km.firebaseapp.com,"
            "http://localhost:5173,http://localhost:3000"
        ),
        "VLLM_BASE_URL": "http://127.0.0.1:8000/v1",
        "VLLM_API_KEY": "legalai-local-colab",
    })
    API_LOG_HANDLE = API_LOG.open("w", encoding="utf-8", buffering=1)
    API_PROCESS = subprocess.Popen([
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", str(API_PORT), "--workers", "1",
    ], cwd=BACKEND, env=environment, stdout=API_LOG_HANDLE, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline and not legalai_ready(API_ROOT):
        if API_PROCESS.poll() is not None:
            raise RuntimeError("API stopped during startup:\n" + API_LOG.read_text(encoding="utf-8")[-8000:])
        time.sleep(1)
    if not legalai_ready(API_ROOT):
        raise TimeoutError("API did not become ready:\n" + API_LOG.read_text(encoding="utf-8")[-8000:])

with urllib.request.urlopen(API_ROOT + "/health?deep=true", timeout=30) as response:
    smoke_result = json.loads(response.read())
if not smoke_result.get("model", {}).get("ready"):
    raise RuntimeError("The backend started but the model is not ready")
print("LegalAI backend ready:", API_ROOT)
print("Google sign-in enabled; reviewer access is limited to the configured account.")
