"""Generate the uploadable one-click Colab notebook using only stdlib JSON."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "colab" / "Krishna_Train_Resume.ipynb"
BOOTSTRAP = ROOT / "colab" / "drive_handoff_bootstrap.py"


def code(source: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": source.splitlines(keepends=True)}


def markdown(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def main() -> None:
    bootstrap_source = BOOTSTRAP.read_text(encoding="utf-8")
    cells = [markdown("""# Krishna's BNS/IT complaint assistant: resumable Colab training

**Normal use:** create a private Google Drive folder named `LegalAI` directly inside `MyDrive`. Upload both `Krishna_Train_Resume.ipynb` and `colab_training_input_v5.zip` into it. The shared source link is only used when this ZIP is absent.

**Continue on another person's account:** stop the source run only after a completed Drive checkpoint. Share the entire source `LegalAI` folder directly with that person's Google account as **Viewer**, with viewer download/copy allowed. Paste its folder link into `SHARED_SOURCE_FOLDER_URL`. When that account has no usable `MyDrive/LegalAI`, the notebook copies the complete shared project into a new folder owned by that account. Existing `MyDrive/LegalAI` projects continue normally and are never replaced.

Open the notebook in Colab, select **Runtime → Change runtime type → GPU**, then choose **Runtime → Run all**. Approve the Drive mount prompt and, only during a shared-folder handoff, the additional Google API authorization prompt.

The notebook trains the complaint-only LoRA first, then the optional BNS/IT Q&A comparison. It saves full checkpoints in `LegalAI/runs/` every 50 optimizer steps. If Colab disconnects, reconnect a GPU and choose **Run all** again. Completed runs are skipped; incomplete runs restart from the latest verified Drive checkpoint. The 90 sealed cases are evaluated only after both development results choose a model. The final adapter and results remain in Drive.

Google Colab can terminate without warning, so only completed checkpoints are guaranteed. This faster mode keeps the same model, data, optimizer, effective batch size and epochs as v3. If the GPU runs out of memory, it automatically retries from the last completed checkpoint using the earlier memory-saving setting.
"""), code("""SHARED_SOURCE_FOLDER_URL = "https://drive.google.com/drive/folders/1nsyR4P7YP8thOb7iWPF84W1f5TjXnE-g?usp=sharing" # @param {type:"string"}
from pathlib import Path
from google.colab import drive
drive.mount('/content/drive')
PROJECT = Path('/content/drive/MyDrive/LegalAI')
print('Drive ready:', PROJECT)
"""), code("""import subprocess, sys
REQUIREMENTS = [
    'transformers==4.57.6', 'trl==0.29.1', 'peft==0.18.1',
    'datasets==4.6.1', 'accelerate==1.12.0', 'bitsandbytes==0.49.2',
]
HANDOFF_NEEDED = (not (PROJECT / 'colab_training_input_v5.zip').is_file()
                  and bool(SHARED_SOURCE_FOLDER_URL.strip()))
if HANDOFF_NEEDED:
    REQUIREMENTS.append('google-api-python-client==2.200.0')
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *REQUIREMENTS])
import importlib.metadata as metadata
package_names = ['transformers','trl','peft','datasets','accelerate','bitsandbytes']
if HANDOFF_NEEDED:
    package_names.append('google-api-python-client')
for name in package_names:
    print(name, metadata.version(name))
"""), code(bootstrap_source + """

ensure_legal_ai_folder(PROJECT, 'colab_training_input_v5.zip', SHARED_SOURCE_FOLDER_URL)
INPUT_ZIP = PROJECT / 'colab_training_input_v5.zip'
"""), code("""import hashlib, json, shutil, zipfile
import torch
if not torch.cuda.is_available():
    raise RuntimeError('GPU is not active. Select Runtime > Change runtime type > GPU, then Run all again.')
print('GPU:', torch.cuda.get_device_name(0))
print('GPU memory (GB):', round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1))
LOCAL = Path('/content/legal_ai_input')
LOCAL.mkdir(parents=True, exist_ok=True)
LOCAL_ZIP = LOCAL / INPUT_ZIP.name
shutil.copyfile(INPUT_ZIP, LOCAL_ZIP)
with zipfile.ZipFile(LOCAL_ZIP) as archive:
    if archive.testzip() is not None:
        raise ValueError('Dataset ZIP failed CRC check')
    for name in archive.namelist():
        if name.startswith('/') or '..' in Path(name).parts:
            raise ValueError('Unsafe ZIP entry: ' + name)
    archive.extractall(LOCAL)
INPUT = LOCAL / 'colab_training_input_v5'
manifest = json.loads((INPUT / 'manifest.json').read_text(encoding='utf-8'))
for rel, expected in manifest['files_sha256'].items():
    actual = hashlib.sha256((INPUT / rel).read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError('Dataset file hash mismatch: ' + rel)
print('Frozen dataset verified:', manifest['counts'])
"""), code("""import sys
sys.path.insert(0, str(INPUT))
sys.modules.pop('train_runner', None)  # Refresh code if this Colab session ran an older ZIP.
import train_runner
results = train_runner.run(INPUT, PROJECT)
print('Training and evaluation finished. Files are in:', PROJECT)
""")]
    notebook = {"cells": cells, "metadata": {"accelerator": "GPU",
               "colab": {"gpuType": "T4", "provenance": []},
               "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
               "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
