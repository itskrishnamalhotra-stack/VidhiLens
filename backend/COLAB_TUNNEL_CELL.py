"""Run after the secure backend cell to create a temporary HTTPS test endpoint."""

import json
import os
import re
import stat
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if "API_ROOT" not in globals() or "DEMO_ACCESS_TOKEN" not in globals():
    raise RuntimeError("Run the Start the backend API cell first")

with urllib.request.urlopen(API_ROOT + "/health", timeout=5) as response:
    local_health = json.loads(response.read())
if local_health.get("build_id") != "nyayasetu_draft_intake_2026_09_29":
    raise RuntimeError("The secure backend build is not running")

CLOUDFLARED = Path("/content/cloudflared")
if not CLOUDFLARED.is_file():
    download_url = (
        "https://github.com/cloudflare/cloudflared/releases/latest/download/"
        "cloudflared-linux-amd64"
    )
    print("Downloading the official Cloudflare quick-tunnel client...")
    urllib.request.urlretrieve(download_url, CLOUDFLARED)
    CLOUDFLARED.chmod(CLOUDFLARED.stat().st_mode | stat.S_IXUSR)

version = subprocess.check_output([str(CLOUDFLARED), "--version"], text=True).strip()
print("Tunnel client:", version)

TUNNEL_LOG = Path("/content/legal_ai_cloudflared.log")
TUNNEL_LOG_HANDLE = TUNNEL_LOG.open("w", encoding="utf-8", buffering=1)
TUNNEL_PROCESS = subprocess.Popen([
    str(CLOUDFLARED), "tunnel", "--url", API_ROOT,
    "--no-autoupdate", "--loglevel", "info",
], stdout=TUNNEL_LOG_HANDLE, stderr=subprocess.STDOUT)

TUNNEL_URL = None
deadline = time.monotonic() + 90
pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
while time.monotonic() < deadline:
    if TUNNEL_PROCESS.poll() is not None:
        raise RuntimeError("Tunnel stopped:\n" + TUNNEL_LOG.read_text(encoding="utf-8")[-8000:])
    log_text = TUNNEL_LOG.read_text(encoding="utf-8", errors="replace") if TUNNEL_LOG.is_file() else ""
    match = pattern.search(log_text)
    if match:
        TUNNEL_URL = match.group(0)
        break
    time.sleep(1)
if not TUNNEL_URL:
    raise TimeoutError("Tunnel URL was not created:\n" + TUNNEL_LOG.read_text(encoding="utf-8")[-8000:])

def request_json(method, path, user="krishna", body=None, token=DEMO_ACCESS_TOKEN, timeout=180):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        TUNNEL_URL + path,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "X-LegalAI-Demo-User": user,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
        return response.status, json.loads(payload) if payload else None

# Confirm the URL is genuinely external and the model server is visible through it.
external_health = None
health_deadline = time.monotonic() + 60
while time.monotonic() < health_deadline:
    try:
        with urllib.request.urlopen(TUNNEL_URL + "/health?deep=true", timeout=30) as response:
            external_health = json.loads(response.read())
        break
    except Exception:
        time.sleep(2)
if external_health is None:
    raise RuntimeError("The tunnel URL was created but did not reach the LegalAI health endpoint")
try:
    request_json("POST", "/sessions", token="wrong-token", body={"title": "blocked"})
    bad_token_rejected = False
except Exception as error:
    bad_token_rejected = getattr(error, "code", None) == 401

# The shared demo token is bound to Krishna's private demo account.
_, test_session = request_json("POST", "/sessions", body={"title": "Phone test"})
test_session_id = test_session["session_id"]
try:
    request_json("GET", f"/sessions/{test_session_id}", user="someone-else")
    impersonation_blocked = False
except Exception as error:
    impersonation_blocked = getattr(error, "code", None) == 401

# Full external LoRA + RAG request and draft lifecycle.
_, turn = request_json(
    "POST", f"/sessions/{test_session_id}/messages",
    body={"text": "Someone stole my phone from my desk without my consent."},
)
analysis = turn["assistant_message"]["structured"]["analysis"]
_, draft = request_json(
    "POST", "/drafts",
    body={"session_id": test_session_id, "details": {"reporter_name": "Test User"}},
)
_, saved_draft = request_json(
    "POST", f"/drafts/{draft['draft_id']}/confirm",
    body={"expected_version": draft["version"], "explicit_confirmation": True},
)

# Conversation UX: ordinary chat must stay outside legal analysis, while a
# later incident in the same session must still enter the LoRA + RAG pipeline.
_, chat_session = request_json(
    "POST", "/sessions",
    body={"title": "Conversation routing check"},
)
chat_session_id = chat_session["session_id"]
conversation_inputs = [
    "Hello",
    "How are you?",
    "Who are you?",
    "Okay, great",
    "I don't understand",
    "What can we talk about today?",
]
conversation_results = []
for text in conversation_inputs:
    _, chat_turn = request_json(
        "POST", f"/sessions/{chat_session_id}/messages",
        body={"text": text},
    )
    structured = chat_turn["assistant_message"]["structured"]
    conversation_results.append({
        "input": text,
        "action": structured.get("action"),
        "kind": structured.get("conversation_kind"),
        "analysis_id": structured.get("analysis_id"),
    })

conversation_all_without_legal_analysis = all(
    item["action"] == "conversation" and item["analysis_id"] is None
    for item in conversation_results
)
_, transition_turn = request_json(
    "POST", f"/sessions/{chat_session_id}/messages",
    body={"text": "Someone stole my phone from my desk without my consent."},
)
transition_analysis = transition_turn["assistant_message"]["structured"]["analysis"]
conversation_incident_transition = (
    transition_analysis["outcome"] == "provision_match"
    and "BNS_303" in transition_analysis["possible_provision_ids"]
)

# Four simultaneous requests exercise API concurrency and vLLM batching.
complaints = [
    "Someone stole my wallet from my desk without consent.",
    "A person pretended to be my bank manager online and cheated me into transferring money.",
    "Someone used my password without permission to enter my email account.",
    "This is a recipe for vegetable soup.",
]
def concurrent_case(index):
    return request_json("POST", "/analyze", body={"complaint": complaints[index]})[1]

concurrent_started = time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as executor:
    concurrent_results = list(executor.map(concurrent_case, range(4)))
concurrent_seconds = time.perf_counter() - concurrent_started

TUNNEL_TEST_REPORT = {
    "tunnel_url": TUNNEL_URL,
    "health": external_health,
    "bad_token_rejected": bad_token_rejected,
    "impersonation_blocked": impersonation_blocked,
    "complaint_outcome": analysis["outcome"],
    "complaint_provisions": analysis["possible_provision_ids"],
    "draft_saved_locally": saved_draft["status"] == "saved",
    "official_filing_performed": False,
    "conversation_results": conversation_results,
    "conversation_all_without_legal_analysis": conversation_all_without_legal_analysis,
    "conversation_incident_transition": conversation_incident_transition,
    "concurrent_requests": len(concurrent_results),
    "concurrent_outcomes": [item["outcome"] for item in concurrent_results],
    "concurrent_wall_seconds": round(concurrent_seconds, 3),
    "all_checks_passed": all([
        external_health.get("api") == "ready",
        external_health.get("model", {}).get("ready", True),
        bad_token_rejected,
        impersonation_blocked,
        analysis["outcome"] == "provision_match",
        "BNS_303" in analysis["possible_provision_ids"],
        saved_draft["status"] == "saved",
        conversation_all_without_legal_analysis,
        conversation_incident_transition,
        len(concurrent_results) == 4,
    ]),
}

report_path = PROJECT / "tunnel_test_report.json"
report_path.write_text(json.dumps(TUNNEL_TEST_REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(TUNNEL_TEST_REPORT, ensure_ascii=False, indent=2))
print("Saved:", report_path)
print("Keep this runtime open while using the temporary endpoint.")
