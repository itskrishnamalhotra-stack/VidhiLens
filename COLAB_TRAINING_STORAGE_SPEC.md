# Colab training storage contract

Owner: Krishna Malhotra. Current preference: use a **private Google Drive folder mounted in Colab** with `drive.mount()`. The earlier link-only constraint has been withdrawn.

1. At each fresh runtime, mount the signed-in user's Drive and locate the project folder. Copy the frozen dataset ZIP to Colab's temporary local disk, verify its manifest hashes, and extract it there for training speed.
2. Reinstall pinned Python packages, verify their versions, download the same base model revision, and check that the dataset and run settings match the checkpoint before resuming.
3. Train on local Colab disk. Save full Trainer checkpoints at regular optimizer-step intervals: adapter weights/config, optimizer, scheduler, random state and trainer step/epoch state.
4. After a local checkpoint is complete, copy it to a temporary path in Drive, verify size and SHA-256, then mark it complete. Retain the two latest complete checkpoints. Ignore any interrupted copy.
5. At a new session, copy the latest valid checkpoint from Drive to local disk and resume Trainer from it. If Colab stops without warning, steps after the last completed copy must be repeated.
6. Keep the 90 sealed evaluation cases outside the training archive. Save final adapter and measured results to Drive when model selection is complete.

Colab may stop the GPU runtime without a final callback. No notebook can guarantee a new checkpoint at the exact quota cutoff. Periodic completed checkpoints are the recovery guarantee. Before a voluntary stop, wait until a completed Drive checkpoint is reported.

Official references: [Colab FAQ](https://research.google.com/colaboratory/faq.html) and [Hugging Face Trainer checkpoint resume](https://huggingface.co/docs/transformers/trainer_recipes).
