"""Append a final Colab access cell while preserving existing run outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ACCESS_SOURCE = '''# Run all ends here. You can also run this cell alone in an existing runtime.
from pathlib import Path
import json
import re
import time
import urllib.request

FRONTEND_URL = "https://vidhilens-legal-ai-km.web.app"
EXPECTED_BUILD = "nyayasetu_draft_intake_2026_09_29"
PROJECT = Path("/content/drive/MyDrive/LegalAI")

def healthy(url, timeout=8):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=timeout) as response:
            status = json.loads(response.read())
        return status.get("api") == "ready" and status.get("build_id") == EXPECTED_BUILD
    except Exception:
        return False

API_ROOT = globals().get("API_ROOT", "")
if not API_ROOT or not healthy(API_ROOT, timeout=2):
    API_ROOT = next(
        (url for url in (f"http://127.0.0.1:{port}" for port in range(8080, 8091))
         if healthy(url, timeout=2)),
        "",
    )
if not API_ROOT:
    print("Starting the updated VidhiLens backend without reloading the model...")
    api_cell = PROJECT / "backend" / "COLAB_API_CELL.py"
    if not api_cell.is_file():
        raise FileNotFoundError(f"Missing backend startup code: {api_cell}")
    exec(api_cell.read_text(encoding="utf-8"), globals())
    if not healthy(API_ROOT):
        raise RuntimeError("The updated backend did not become ready. If the model runtime stopped, use Run all.")

token_file = Path("/content/legal_ai_demo_token")
admin_file = Path("/content/legal_ai_admin_token")
DEMO_ACCESS_TOKEN = (
    token_file.read_text(encoding="utf-8").strip() if token_file.is_file()
    else globals().get("DEMO_ACCESS_TOKEN", "")
)
ADMIN_ACCESS_TOKEN = (
    admin_file.read_text(encoding="utf-8").strip() if admin_file.is_file()
    else globals().get("ADMIN_ACCESS_TOKEN", "")
)
if not DEMO_ACCESS_TOKEN or not ADMIN_ACCESS_TOKEN:
    raise RuntimeError("Access tokens are missing. Run the Backend API cell again, then this cell.")

urls = [globals().get("TUNNEL_URL", "")]
log_file = Path("/content/legal_ai_cloudflared.log")
if log_file.is_file():
    urls.extend(re.findall(
        r"https://[a-z0-9-]+\\.trycloudflare\\.com",
        log_file.read_text(encoding="utf-8", errors="replace"),
    ))
TUNNEL_URL = ""
for candidate in reversed(list(dict.fromkeys(url for url in urls if url))):
    if healthy(candidate):
        TUNNEL_URL = candidate
        break

if not TUNNEL_URL:
    print("The previous tunnel is unavailable. Creating a fresh temporary link...")
    tunnel_cell = PROJECT / "backend" / "COLAB_TUNNEL_CELL.py"
    if not tunnel_cell.is_file():
        raise FileNotFoundError(f"Missing tunnel startup code: {tunnel_cell}")
    exec(tunnel_cell.read_text(encoding="utf-8"), globals())
    if not healthy(TUNNEL_URL):
        raise RuntimeError("The new tunnel did not pass its health check")

print("\\n" + "=" * 64)
print("VIDHILENS IS READY")
print("Website:        ", FRONTEND_URL)
print("Backend URL:    ", TUNNEL_URL)
print("Citizen token:  ", DEMO_ACCESS_TOKEN)
print("Reviewer token: ", ADMIN_ACCESS_TOKEN)
print("Keep this Colab runtime connected while using the website.")
print("=" * 64)
'''


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: append_access_details.py NOTEBOOK.ipynb")
    path = Path(sys.argv[1])
    notebook = json.loads(path.read_text(encoding="utf-8"))
    cells = notebook["cells"]
    compile(ACCESS_SOURCE, "access details cell", "exec")
    new_cell = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": ACCESS_SOURCE.splitlines(keepends=True),
    }
    if cells and "VIDHILENS IS READY" in "".join(cells[-1].get("source", [])):
        cells[-1] = new_cell
    else:
        cells.append(new_cell)
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Final access cell present: {path}")


if __name__ == "__main__":
    main()
