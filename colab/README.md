# Colab training: Krishna

## Your two steps

1. In your **private** Google Drive, create `MyDrive/LegalAI`. Upload both [Krishna_Train_Resume.ipynb](Krishna_Train_Resume.ipynb) and [colab_training_input_v5.zip](../exports/colab_training_input_v5.zip) into that folder. Keep their names unchanged. Completed training checkpoints from v4 can be reused.
2. Open `Krishna_Train_Resume.ipynb` with Google Colab. Select **Runtime > Change runtime type > GPU**, then **Runtime > Run all**. Approve the Google Drive mount when prompted.

## Optional account handoff

1. Stop the source training only after the notebook reports a completed Drive checkpoint.
2. Share the complete source `LegalAI` folder directly with the other Google account as **Viewer** and keep viewer download/copy enabled.
3. Share the notebook and put the source folder link in its `SHARED_SOURCE_FOLDER_URL` field.
4. On the other account, select GPU and choose **Run all**. If that account has no usable `MyDrive/LegalAI`, the notebook requests Google API authorization and copies the complete project into that account's own Drive before resuming. If a usable local folder already exists, the shared link is ignored.

The notebook automatically installs its packages, verifies and copies the data ZIP to the Colab VM, checks assistant-token masking before downloading model weights, trains two candidate LoRA adapters, saves complete training checkpoints in `LegalAI/runs/`, evaluates both on the development set, selects one, and writes `LegalAI/training_results.json` after sealed evaluation. The final adapter is at `LegalAI/runs/<chosen variant>/final_adapter.zip`. It first uses GPU memory to avoid recomputing activations; if that runs out of memory, it retries from the last verified Drive checkpoint with the memory-saving setting. V5 passes an explicit attention mask during evaluation and reruns any older evaluation predictions; completed training is reused.

If Colab disconnects or GPU time ends, leave the Drive folder intact. When a GPU is available again, open the same notebook and choose **Run all**. It verifies the newest completed Drive checkpoint and resumes. Work after the last completed checkpoint may need to be repeated. Training and evaluation have been completed; this notebook is retained for reproducibility or further experiments. The current demo startup procedure is in [WARM_PRODUCTION_RUN.md](WARM_PRODUCTION_RUN.md).
