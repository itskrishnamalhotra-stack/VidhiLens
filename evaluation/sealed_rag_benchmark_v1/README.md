# Sealed RAG v2.2 benchmark

## Run

1. Open `Krishna_RAG_v2_2_Sealed_Benchmark.ipynb` from `MyDrive/LegalAI` in Google Colab.
2. Select **Runtime → Change runtime type → T4 GPU**.
3. Select **Runtime → Run all** and approve the Drive mount.
4. Leave the tab running. The evaluator saves after every complaint.
5. If Colab disconnects or the GPU allocation ends, stop the runtime. Later open the same notebook from the account containing the current `LegalAI` folder, select a T4 GPU and choose **Run all**. Completed cases are skipped.
6. Do not set `RESTART_SEALED_BENCHMARK=True` unless the complete evaluation must intentionally restart.

## Outputs

- `MyDrive/LegalAI/sealed_rag_benchmark_v1_predictions.json` contains resumable predictions.
- `MyDrive/LegalAI/sealed_rag_benchmark_v1_report.json` appears after all 150 cases finish and contains every accuracy, retrieval, safety, language and latency metric.

The answer key is never included in a model prompt. It is loaded only after all predictions have been saved. Labels were AI-reviewed against the verified statutory catalogue and were not reviewed by a lawyer.

The evaluator attempts batches of two candidate assessments with identical deterministic prompts. If GPU memory is insufficient, it automatically retries the affected batch one candidate at a time.
