"""Start a temporary HTTPS tunnel and publish it for the Firebase website."""

import json
import os
import re
import stat
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if "API_ROOT" not in globals():
    raise RuntimeError("Run the backend API cell first")

EXPECTED_BUILD = "nyayasetu_draft_intake_2026_09_29"

def endpoint_health(root):
    try:
        with urllib.request.urlopen(root.rstrip("/") + "/health?deep=true", timeout=30) as response:
            body = json.loads(response.read())
        return body if body.get("api") == "ready" and body.get("build_id") == EXPECTED_BUILD and body.get("auth_mode") == "firebase" and body.get("model", {}).get("ready") else None
    except Exception:
        return None

if not endpoint_health(API_ROOT):
    raise RuntimeError("The Firebase backend and model are not ready")

CLOUDFLARED = Path("/content/cloudflared")
if not CLOUDFLARED.is_file():
    print("Downloading the Cloudflare quick-tunnel client...")
    urllib.request.urlretrieve(
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
        CLOUDFLARED,
    )
    CLOUDFLARED.chmod(CLOUDFLARED.stat().st_mode | stat.S_IXUSR)

TUNNEL_LOG = Path("/content/legal_ai_cloudflared.log")
url_pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
existing = globals().get("TUNNEL_URL", "")
if existing and endpoint_health(existing):
    TUNNEL_URL = existing
    print("Reusing healthy tunnel:", TUNNEL_URL)
else:
    TUNNEL_LOG_HANDLE = TUNNEL_LOG.open("w", encoding="utf-8", buffering=1)
    TUNNEL_PROCESS = subprocess.Popen(
        [str(CLOUDFLARED), "tunnel", "--url", API_ROOT, "--no-autoupdate", "--loglevel", "info"],
        stdout=TUNNEL_LOG_HANDLE, stderr=subprocess.STDOUT,
    )
    TUNNEL_URL = ""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if TUNNEL_PROCESS.poll() is not None:
            raise RuntimeError("Tunnel stopped:\n" + TUNNEL_LOG.read_text(encoding="utf-8")[-5000:])
        log_text = TUNNEL_LOG.read_text(encoding="utf-8", errors="replace") if TUNNEL_LOG.is_file() else ""
        match = url_pattern.search(log_text)
        if match and endpoint_health(match.group(0)):
            TUNNEL_URL = match.group(0)
            break
        time.sleep(2)
    if not TUNNEL_URL:
        raise TimeoutError("The new tunnel did not become healthy:\n" + log_text[-5000:])

try:
    urllib.request.urlopen(TUNNEL_URL + "/me", timeout=15)
    raise RuntimeError("The API accepted an unauthenticated request")
except urllib.error.HTTPError as error:
    if error.code != 401:
        raise RuntimeError(f"Unexpected auth check status: {error.code}") from error

import google.auth
from google.cloud import firestore
credential_options = {"scopes": ["https://www.googleapis.com/auth/cloud-platform"]}
if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    credential_options["quota_project_id"] = "nyayasetu-legal-ai-km"
credentials, _ = google.auth.default(**credential_options)
firestore.Client(project="nyayasetu-legal-ai-km", credentials=credentials).collection("runtime").document("active").set({
    "api_base_url": TUNNEL_URL,
    "build_id": EXPECTED_BUILD,
    "published_at": datetime.now(timezone.utc).isoformat(),
})

TUNNEL_TEST_REPORT = {
    "tunnel_url": TUNNEL_URL,
    "health": endpoint_health(TUNNEL_URL),
    "unauthenticated_access_rejected": True,
    "firebase_discovery_published": True,
    "all_checks_passed": True,
}
report_path = PROJECT / "tunnel_test_report.json"
report_path.write_text(json.dumps(TUNNEL_TEST_REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(TUNNEL_TEST_REPORT, ensure_ascii=False, indent=2))
print("VidhiLens connects to this Colab runtime automatically. Keep it running while using the website.")
