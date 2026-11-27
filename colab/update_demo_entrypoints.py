"""Keep Colab startup cells pointed at the mounted Drive backend code."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from firebase_access_cell import ACCESS_SOURCE


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: update_demo_entrypoints.py NOTEBOOK.ipynb")
    path = Path(sys.argv[1])
    notebook = json.loads(path.read_text(encoding="utf-8"))
    cells = notebook["cells"]
    # Older Drive copies contain ad hoc startup cells after the final access
    # cell. They print shared tokens and call the retired demo tunnel script.
    while cells and not "".join(cells[-1].get("source", [])).strip():
        cells.pop()
    if cells and "COLAB_TUNNEL_CELL.py" in "".join(cells[-1].get("source", [])):
        cells.pop()
    if cells and "print(\"Citizen token:\"" in "".join(cells[-1].get("source", [])):
        cells.pop()
    access_indices = [index for index, cell in enumerate(cells)
                      if "VIDHILENS IS READY" in "".join(cell.get("source", []))]
    if len(cells) < 14 or len(access_indices) != 1:
        raise RuntimeError("Unexpected notebook layout; preserve it for manual review")
    cells[0]["source"] = (
        "# VidhiLens: start the app from Colab\n\n"
        "Select **T4 GPU**, click **Connect**, then **Run all**. Approve Google Drive "
        "access when Colab asks. The notebook loads the model, "
        "starts the Firebase-authenticated backend, publishes its temporary address "
        "to the website, and prints the citizen and reviewer website links. "
        "Firebase access comes from a dedicated credential in the private "
        "NyayaSetu Credentials Drive folder, or from the Colab account if it has "
        "project access. There is no URL or token to paste. Keep this runtime connected while using "
        "the app. The full benchmark is skipped by default.\n"
    ).splitlines(keepends=True)
    cells[9]["source"] = (
        "## Automatic website connection\n\n"
        "Run all creates an HTTPS tunnel and publishes its address to Firebase. "
        "The website finds it automatically and checks that the model is healthy.\n"
    ).splitlines(keepends=True)
    for index, filename in ((8, "COLAB_API_CELL.py"), (10, "COLAB_TUNNEL_FIREBASE_CELL.py")):
        source = (
            "from pathlib import Path\n"
            "BACKEND = Path('/content/drive/MyDrive/LegalAI/backend')\n"
            f"exec((BACKEND / '{filename}').read_text(encoding='utf-8'), globals())\n"
        )
        compile(source, f"notebook cell {index}", "exec")
        cells[index]["source"] = source.splitlines(keepends=True)
        cells[index]["execution_count"] = None
        cells[index]["outputs"] = []
    cells[access_indices[0]]["source"] = ACCESS_SOURCE.splitlines(keepends=True)
    cells[access_indices[0]]["execution_count"] = None
    cells[access_indices[0]]["outputs"] = []
    compile(ACCESS_SOURCE, "access details cell", "exec")
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Notebook entrypoints updated: {path}")


if __name__ == "__main__":
    main()
