"""Final notebook cell for automatic Firebase connection."""

ACCESS_SOURCE = '''# Run all ends here. This cell can also reconnect an existing warm runtime.
from pathlib import Path
import json
import urllib.request

PROJECT = Path("/content/drive/MyDrive/LegalAI")
BACKEND = PROJECT / "backend"
SITE = "https://vidhilens-legal-ai-km.web.app"
REVIEWER_SITE = SITE + "/reviewer"

def firebase_api_ready(root):
    try:
        with urllib.request.urlopen(root.rstrip("/") + "/health?deep=true", timeout=15) as response:
            body = json.loads(response.read())
        return body.get("api") == "ready" and body.get("auth_mode") == "firebase" and body.get("model", {}).get("ready")
    except Exception:
        return False

if not firebase_api_ready(globals().get("API_ROOT", "")):
    print("Starting the Firebase backend...")
    exec((BACKEND / "COLAB_API_CELL.py").read_text(encoding="utf-8"), globals())
if not firebase_api_ready(globals().get("TUNNEL_URL", "")):
    print("Starting and publishing the tunnel...")
    exec((BACKEND / "COLAB_TUNNEL_FIREBASE_CELL.py").read_text(encoding="utf-8"), globals())

print("VIDHILENS IS READY")
print("Citizen website:", SITE)
print("Reviewer website:", REVIEWER_SITE)
print("Backend: connected automatically; no URL or token entry is needed.")
print("Keep this Colab runtime connected while using VidhiLens.")
'''
