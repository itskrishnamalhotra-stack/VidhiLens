"""Static checks for the warm vLLM production benchmark notebook."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "colab" / "Krishna_Warm_Production_Benchmark.ipynb"
notebook = json.loads(PATH.read_text(encoding="utf-8"))
assert notebook["nbformat"] == 4
assert notebook["metadata"]["accelerator"] == "GPU"
assert notebook["metadata"]["colab"]["gpuType"] == "T4"
assert len(notebook["cells"]) == 12

for index, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] == "code":
        compile("".join(cell["source"]), f"warm-vllm-cell-{index}", "exec")

source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
for required in (
    "BASE_MODEL = TRAINING_RESULTS['base_model']",
    "vllm==0.30.0",
    "torchvision==0.28.0",
    "torchaudio==2.11.0",
    "torchcodec>=0.14",
    "'--force-reinstall'",
    "'--no-deps', 'torchaudio==2.11.0'",
    "Verified Torch stack:",
    "Torch/TorchVision/TorchAudio verification failed:",
    "--query-gpu=name,memory.total",
    "executable, 'serve', BASE_MODEL",
    "'--enable-prefix-caching'",
    "'--enforce-eager'",
    "'--max-num-seqs', '4'",
    "'--gpu-memory-utilization', '0.80'",
    "'--lora-modules'",
    "f'{LORA_SERVED_NAME}={ADAPTER_PATH}'",
    "SERVER_ROOT + '/health'",
    "SERVER_API + '/chat/completions'",
    "def parse_json(raw):",
    "triage = parse_json(triage_raw)",
    "WARM_PIPELINE_FINGERPRINT = 'grounded_clean_output_2026_09_27'",
    "COMPATIBLE_GENERATION_FINGERPRINTS = {'grounded_compact_assessment_2026_09_27'}",
    "def assessment_response_format(candidates):",
    "'name': 'legal_candidate_assessments'",
    "response_format=assessment_response_format(retrieval['offence_candidates'])",
    "'action': 'grounded_triage_fallback'",
    "apply_output_cleaner(",
    "output_cleaner_migrated",
    "No repeated GPU generation was needed.",
    "answer_key_acceptable_positive_section_accuracy",
    "def assemble(complaint, retrieval, assessments, triage):",
    "ASSESS_PARAMS = 220",
    "warm_vllm_previous_predictions.json",
    "start_new_session=True",
    "vllm_server.log",
    "server_failure_report",
    "WARMUP = run_warm_query",
    "warmup_excluded",
    "warm_vllm_predictions.json",
    "warm_vllm_report.json",
    "quality_preserved_against_established_baseline",
    "Run warm production query",
    "PROJECT / 'backend/app/main.py'",
    '"LEGALAI_DATABASE_PATH": str(PROJECT / "app_data" / "legalai.sqlite")',
    '"VLLM_BASE_URL": "http://127.0.0.1:8000/v1"',
    "LegalAI backend ready:",
    "def port_is_free(port):",
    "for candidate in range(8080, 8091):",
    "without stopping\n# or interfering with another notebook service",
    "secure_demo_gateway_2026_09_28_conversation_router",
    "cloudflared-linux-amd64",
    "cross_user_access_blocked",
    "concurrent_requests",
    "tunnel_test_report.json",
):
    assert required in source, required

for forbidden in (
    "from vllm import",
    "VLLM_ENABLE_V1_MULTIPROCESSING",
    "create_vllm_engine_in_colab",
    "Fix these validation errors:",
    "evidence is not an exact complaint quote",
    "ASSESS_PARAMS = 650",
):
    assert forbidden not in source, forbidden

# The same locally tested retriever and deterministic legal gates are embedded.
core = (ROOT / "scripts" / "rag_improved_core.py").read_text(encoding="utf-8")
assert core in source
print("Warm vLLM notebook checks passed")
