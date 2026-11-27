"""Create a standalone Colab notebook for warm vLLM serving and quality checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = (ROOT / "scripts" / "rag_improved_core.py").read_text(encoding="utf-8")
BACKEND_API = (ROOT / "backend" / "COLAB_API_CELL.py").read_text(encoding="utf-8")
TUNNEL_API = (ROOT / "backend" / "COLAB_TUNNEL_CELL.py").read_text(encoding="utf-8")


def md(source: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(True)}


def code(source: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": source.splitlines(True)}


MOUNT = r'''from pathlib import Path
from google.colab import drive

drive.mount('/content/drive')
PROJECT = Path('/content/drive/MyDrive/LegalAI')
REQUIRED = [
    PROJECT / 'training_results.json',
    PROJECT / 'rag_catalogue_v1.json',
    PROJECT / 'runs/complaint_only/final_adapter.zip',
    PROJECT / 'sealed_rag_benchmark_v1/benchmark_inputs.jsonl',
    PROJECT / 'sealed_rag_benchmark_v1/sealed_answer_key.jsonl',
    PROJECT / 'backend/app/main.py',
]
missing = [str(path) for path in REQUIRED if not path.is_file()]
if missing:
    raise FileNotFoundError('Missing required Drive files:\n' + '\n'.join(missing))
print('Drive project verified:', PROJECT)
'''


INSTALL = r'''import subprocess, sys

# Install before importing torch or vLLM. This notebook is deliberately
# separate from training so the serving engine owns the GPU runtime.
subprocess.check_call([
    sys.executable, '-m', 'pip', 'install', '-q', '--upgrade',
    'vllm==0.30.0',
    'torchvision==0.28.0',
    'torchaudio==2.11.0',
    'torchcodec>=0.14',
    'ipywidgets'
])
# Colab can already have the same TorchAudio package version compiled for its
# original CUDA 12.8 PyTorch. A normal --upgrade then keeps that incompatible
# wheel. Force replacement after vLLM has installed its CUDA 13 PyTorch stack.
subprocess.check_call([
    sys.executable, '-m', 'pip', 'install', '-q', '--force-reinstall',
    '--no-deps', 'torchaudio==2.11.0'
])
# vLLM imports TorchVision during kernel warm-up even for text models. Verify
# TorchAudio too because Transformers imports it while vLLM starts. TorchCodec
# remains installed, but importing it is an unnecessary FFmpeg check here.
verification = subprocess.run([
    sys.executable, '-c',
    'import torch, torchvision, torchaudio; '
    'print("Verified Torch stack:", torch.__version__, torch.version.cuda, '
    'torchvision.__version__, torchaudio.__version__)'
], text=True, capture_output=True)
if verification.returncode:
    raise RuntimeError(
        'Torch/TorchVision/TorchAudio verification failed:\n' + verification.stderr)
print(verification.stdout.strip())
import importlib.metadata as metadata
print('vLLM:', metadata.version('vllm'))
print('vLLM dependency stack is ready.')
'''


LOAD_DATA = r'''import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

# Query the GPU through nvidia-smi so this notebook process does not initialize
# CUDA before vLLM creates its engine.
try:
    gpu_line = subprocess.check_output([
        'nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'
    ], text=True).strip()
except Exception as error:
    raise RuntimeError('Select Runtime > Change runtime type > T4 GPU, then Run all.') from error
print('GPU:', gpu_line)

TRAINING_RESULTS = json.loads((PROJECT / 'training_results.json').read_text(encoding='utf-8'))
BASE_MODEL = TRAINING_RESULTS['base_model']
BASE_REVISION = TRAINING_RESULTS['base_revision']
ADAPTER_ZIP = PROJECT / TRAINING_RESULTS['adapter']
ADAPTER_SHA256 = hashlib.sha256(ADAPTER_ZIP.read_bytes()).hexdigest()

LOCAL_ROOT = Path('/content/legal_ai_warm_server')
ADAPTER_PARENT = LOCAL_ROOT / 'adapter'
if ADAPTER_PARENT.exists():
    shutil.rmtree(ADAPTER_PARENT)
ADAPTER_PARENT.mkdir(parents=True)
with zipfile.ZipFile(ADAPTER_ZIP) as archive:
    if archive.testzip() is not None:
        raise ValueError('Adapter ZIP failed its CRC check')
    for name in archive.namelist():
        if name.startswith('/') or '..' in Path(name).parts:
            raise ValueError('Unsafe adapter ZIP entry: ' + name)
    archive.extractall(ADAPTER_PARENT)
ADAPTER_PATH = ADAPTER_PARENT / 'final_adapter'
adapter_config = json.loads((ADAPTER_PATH / 'adapter_config.json').read_text(encoding='utf-8'))
if adapter_config['base_model_name_or_path'] != BASE_MODEL:
    raise ValueError('Adapter/base-model mismatch')

catalogue_payload = json.loads((PROJECT / 'rag_catalogue_v1.json').read_text(encoding='utf-8'))
RAG_ROWS = catalogue_payload['provisions']
RAG_CATALOGUE = {row['provision_id']: row for row in RAG_ROWS}

def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

BENCHMARK_INPUTS = read_jsonl(PROJECT / 'sealed_rag_benchmark_v1/benchmark_inputs.jsonl')
BENCHMARK_GOLD = read_jsonl(PROJECT / 'sealed_rag_benchmark_v1/sealed_answer_key.jsonl')
GOLD_BY_ID = {row['case_id']: row for row in BENCHMARK_GOLD}
print('Base model:', BASE_MODEL, BASE_REVISION)
print('Adapter rank:', adapter_config['r'])
print('Benchmark cases:', len(BENCHMARK_INPUTS))
'''


PIPELINE = r'''# Colab/Jupyter cells are not importable child-process entry points.
# vLLM officially supports disabling its V1 scheduler subprocess for this use.
os.environ['VLLM_ENABLE_V1_MULTIPROCESSING'] = '0'

import sys
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest

TRIAGE_SYSTEM_PROMPT = (
    'Read the reported incident. Return JSON only with outcome, '
    'possible_provision_ids, and uncertain_sections. '
    'A section is only a possibility, never a finding of guilt. '
    'Never invent missing facts.'
)

JOINT_CANDIDATE_SYSTEM_PROMPT = """Assess every supplied candidate provision against the reported incident.
This is cautious possible-section triage, not guilt and not legal advice.
For each candidate return only provision_id and decision.
decision is supported, missing_facts, or rejected.
supported requires all material checklist elements in the reported incident.
missing_facts means a material element could be established by one focused factual question.
rejected is used for contradiction, a shared keyword, or no reasonable factual link.
Do not infer cheating from delay alone, breach of trust from late return alone, physical theft from a bank transfer, or sexually explicit conduct from merely private or obscene material.
Return compact JSON only in this exact form:
{"assessments":[{"provision_id":"...","decision":"supported|missing_facts|rejected"}]}
Return exactly one assessment for every supplied candidate and no extra IDs."""

IMPROVED_RETRIEVER = build_retriever(RAG_ROWS)
VALID_PROVISION_IDS = set(IMPROVED_RETRIEVER['index'])
LORA_REQUEST = LoRARequest('legal-complaint-lora', 1, str(ADAPTER_PATH))

print('Loading one persistent vLLM engine. The one-time load is excluded from latency results...')

def create_vllm_engine_in_colab():
    # vLLM 0.30's in-process distributed setup temporarily suppresses stdout by
    # file descriptor. IPython's OutStream deliberately has no fileno(), so give
    # engine construction a real descriptor and restore notebook capture after.
    notebook_stdout = sys.stdout
    fd_stdout = open('/dev/stdout', 'w', buffering=1)
    sys.stdout = fd_stdout
    try:
        return LLM(
            model=BASE_MODEL,
            revision=BASE_REVISION,
            dtype='float16',
            max_model_len=4096,
            gpu_memory_utilization=0.92,
            enable_lora=True,
            max_lora_rank=int(adapter_config['r']),
            enable_prefix_caching=True,
            seed=42,
        )
    finally:
        sys.stdout = notebook_stdout
        fd_stdout.close()

ENGINE = create_vllm_engine_in_colab()
TRIAGE_PARAMS = SamplingParams(temperature=0.0, max_tokens=140)
ASSESS_PARAMS = SamplingParams(temperature=0.0, max_tokens=220)

def parse_json(raw):
    value = raw.strip()
    if value.startswith('```'):
        value = re.sub(r'^```(?:json)?\s*|\s*```$', '', value, flags=re.I | re.S).strip()
    try:
        return json.loads(value)
    except Exception:
        start, end = value.find('{'), value.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(value[start:end + 1])
            except Exception:
                return None
        return None

def chat(messages, params, use_lora, response_format=None):
    started = time.perf_counter()
    outputs = ENGINE.chat(
        messages,
        sampling_params=params,
        lora_request=LORA_REQUEST if use_lora else None,
        use_tqdm=False,
    )
    text = outputs[0].outputs[0].text.strip()
    return text, time.perf_counter() - started, len(outputs[0].outputs[0].token_ids)

def candidate_messages(complaint, candidates, context_candidates, triage):
    payload = {
        'reported_incident': complaint,
        'candidates': [{
            'provision_id': item['provision_id'],
            'title': item['title'],
            'legal_text': re.sub(r'\s+', ' ', item['verified_text']).strip()[:1800],
            'element_checklist': item['element_checklist'],
            'retrieval_signals': {
                'concept_hit_count': item['concept_hit_count'],
                'uncertainty_hit_count': item['uncertainty_hit_count'],
                'triage_seed': item['triage_seed'],
                'companion_candidate': item['companion_candidate'],
            },
        } for item in candidates],
        'supporting_context': [{
            'provision_id': item['provision_id'],
            'title': item['title'],
            'legal_text': re.sub(r'\s+', ' ', item['verified_text']).strip()[:1500],
        } for item in context_candidates],
        'lora_triage_prior': triage if isinstance(triage, dict) else None,
    }
    return [
        {'role': 'system', 'content': JOINT_CANDIDATE_SYSTEM_PROMPT},
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
    ]

def assessment_response_format(candidates):
    candidate_ids = [item['provision_id'] for item in candidates]
    count = len(candidate_ids)
    return {
        'type': 'json_schema',
        'json_schema': {
            'name': 'legal_candidate_assessments',
            'strict': True,
            'schema': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['assessments'],
                'properties': {
                    'assessments': {
                        'type': 'array',
                        'minItems': count,
                        'maxItems': count,
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'required': ['provision_id', 'decision'],
                            'properties': {
                                'provision_id': {'type': 'string', 'enum': candidate_ids},
                                'decision': {
                                    'type': 'string',
                                    'enum': ['supported', 'missing_facts', 'rejected'],
                                },
                            },
                        },
                    },
                },
            },
        },
    }

def assessment_errors(item, expected_id, complaint):
    if not isinstance(item, dict):
        return ['assessment is not an object']
    errors = []
    if item.get('provision_id') != expected_id:
        errors.append('wrong provision_id')
    decision = item.get('decision')
    if decision not in {'supported', 'missing_facts', 'rejected'}:
        errors.append('invalid decision')
    return errors

def unpack_assessments(candidates, complaint, raw):
    parsed = parse_json(raw)
    rows = parsed.get('assessments') if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        return [], ['root must contain assessments list']
    by_id = {x.get('provision_id'): x for x in rows if isinstance(x, dict)}
    expected = [x['provision_id'] for x in candidates]
    root_errors = [] if set(by_id) == set(expected) else ['assessment IDs differ from candidates']
    records = []
    for candidate in candidates:
        parsed_item = by_id.get(candidate['provision_id'])
        errors = assessment_errors(parsed_item, candidate['provision_id'], complaint)
        records.append({
            **{key: candidate[key] for key in (
                'provision_id', 'title', 'recommendable', 'retrieval_score',
                'concept_hit_count', 'uncertainty_hit_count', 'triage_seed',
                'companion_candidate')},
            'raw_model_output': raw,
            'parsed_assessment': parsed_item,
            'schema_valid': not errors,
            'schema_errors': errors,
        })
    return records, root_errors + [e for row in records for e in row['schema_errors']]

def validate_final(final):
    errors = []
    if not isinstance(final, dict):
        return {'valid': False, 'errors': ['final output is not an object']}
    if final.get('outcome') not in {'provision_match', 'insufficient_information', 'out_of_scope'}:
        errors.append('invalid outcome')
    ids = final.get('possible_provision_ids')
    if not isinstance(ids, list):
        errors.append('possible_provision_ids is not a list'); ids = []
    if not isinstance(final.get('uncertain_sections'), list):
        errors.append('uncertain_sections is not a list')
    for provision_id in ids:
        row = RAG_CATALOGUE.get(provision_id)
        if not row or provision_id not in VALID_PROVISION_IDS:
            errors.append('invalid provision: ' + str(provision_id))
    return {'valid': not errors, 'errors': errors}

def assemble(complaint, retrieval, assessments, triage):
    supported, questions, actions = [], {}, []
    for item in assessments:
        parsed = item.get('parsed_assessment')
        if not item.get('schema_valid') or not isinstance(parsed, dict):
            actions.append({'provision_id': item['provision_id'], 'action': 'schema_blocked'})
            continue
        provision_id = item['provision_id']
        decision = parsed['decision']
        state = cue_state(complaint, provision_id)
        if decision == 'supported':
            if not (state['positive'] or item.get('triage_seed')):
                actions.append({'provision_id': provision_id, 'action': 'unsupported_without_signal_removed'})
            else:
                supported.append(provision_id)
        elif decision == 'missing_facts':
            questions[provision_id] = DEFAULT_MISSING_QUESTIONS[provision_id]
        elif state['uncertain']:
            questions[provision_id] = DEFAULT_MISSING_QUESTIONS[provision_id]
    supported, questions, gate_actions = apply_deterministic_gates(complaint, supported, questions)
    actions.extend(gate_actions)

    triage_outcome = triage.get('outcome') if isinstance(triage, dict) else None
    candidate_ids = {item['provision_id'] for item in retrieval['offence_candidates']}
    if triage_outcome == 'provision_match':
        for provision_id in triage_seed_ids(triage):
            if (provision_id in candidate_ids and provision_id in VALID_PROVISION_IDS
                    and cue_state(complaint, provision_id)['positive']
                    and provision_id not in supported):
                supported.append(provision_id)
                actions.append({'provision_id': provision_id, 'action': 'grounded_triage_fallback'})
        supported, questions, fallback_actions = apply_deterministic_gates(
            complaint, supported, questions)
        actions.extend(fallback_actions)
        supported, questions, cleaner_actions = apply_output_cleaner(
            complaint, supported, questions,
            [item['provision_id'] for item in retrieval['offence_candidates']])
        actions.extend(cleaner_actions)

    supported = list(dict.fromkeys(supported))
    uncertain = [
        {'provision_id': pid, 'missing_facts': question}
        for pid, question in questions.items() if pid not in supported
    ]
    # The fine-tuned LoRA is the trained outcome classifier.  Candidate
    # assessment refines its section set; it must not silently convert a valid
    # insufficient/out-of-scope decision into a positive complaint.
    if (triage_outcome == 'insufficient_information' and not uncertain
            and not has_scoped_legal_subject(complaint)):
        final = {'outcome': 'out_of_scope', 'possible_provision_ids': [],
                 'uncertain_sections': []}
    elif triage_outcome == 'insufficient_information':
        final = {'outcome': 'insufficient_information', 'possible_provision_ids': [],
                 'uncertain_sections': uncertain}
    elif (triage_outcome != 'provision_match' and uncertain
            and explicit_transaction_uncertainty(complaint)):
        final = {'outcome': 'insufficient_information', 'possible_provision_ids': [],
                 'uncertain_sections': uncertain}
    elif triage_outcome != 'provision_match':
        final = {'outcome': 'out_of_scope', 'possible_provision_ids': [],
                 'uncertain_sections': []}
    elif supported:
        final = {'outcome': 'provision_match', 'possible_provision_ids': supported,
                 'uncertain_sections': uncertain}
    elif uncertain:
        final = {'outcome': 'insufficient_information', 'possible_provision_ids': [],
                 'uncertain_sections': uncertain}
    else:
        final = {'outcome': 'out_of_scope', 'possible_provision_ids': [],
                 'uncertain_sections': []}
    return final, actions, validate_final(final)

def run_warm_query(complaint):
    total_start = time.perf_counter()
    triage_raw, triage_seconds, triage_tokens = chat([
        {'role': 'system', 'content': TRIAGE_SYSTEM_PROMPT},
        {'role': 'user', 'content': complaint},
    ], TRIAGE_PARAMS, True)
    triage = parse_json(triage_raw)
    if not isinstance(triage, dict):
        triage = {}
    retrieval_start = time.perf_counter()
    retrieval = retrieve_candidates(complaint, triage, IMPROVED_RETRIEVER)
    retrieval_seconds = time.perf_counter() - retrieval_start
    assessments, assessment_seconds, assessment_tokens = [], 0.0, 0
    if retrieval['offence_candidates']:
        messages = candidate_messages(
            complaint, retrieval['offence_candidates'], retrieval['context_candidates'], triage)
        raw, seconds, tokens_out = chat(
            messages, ASSESS_PARAMS, False,
            response_format=assessment_response_format(retrieval['offence_candidates']))
        assessment_seconds += seconds; assessment_tokens += tokens_out
        assessments, errors = unpack_assessments(retrieval['offence_candidates'], complaint, raw)
    final, actions, validation = assemble(complaint, retrieval, assessments, triage)
    return {
        'triage': triage,
        'triage_raw': triage_raw,
        'retrieved_provision_ids': [x['provision_id'] for x in retrieval['offence_candidates']],
        'candidate_assessments': assessments,
        'evidence_gate_actions': actions,
        'final_output': final,
        'final_validation': validation,
        'repair_used': False,
        'timing': {
            'triage_seconds': triage_seconds,
            'retrieval_seconds': retrieval_seconds,
            'assessment_seconds': assessment_seconds,
            'total_seconds': time.perf_counter() - total_start,
            'output_tokens': triage_tokens + assessment_tokens,
        },
    }

# Explicit warm-up. Its time is never included in warm-query statistics.
print('Warming engine and both base/LoRA execution paths...')
WARMUP = run_warm_query(BENCHMARK_INPUTS[0]['complaint'])
print('Warm-up complete. Excluded time:', round(WARMUP['timing']['total_seconds'], 2), 'seconds')
'''


# Launch vLLM through its supported CLI in a separate process. The notebook
# kernel never imports vLLM or initializes CUDA; it calls the local HTTP API.
_SERVER_PROMPTS = PIPELINE[
    PIPELINE.index("TRIAGE_SYSTEM_PROMPT"):PIPELINE.index("IMPROVED_RETRIEVER")
]
_SERVER_PARSE_JSON = PIPELINE[
    PIPELINE.index("def parse_json"):PIPELINE.index("def chat")
]
_SERVER_FUNCTIONS = PIPELINE[PIPELINE.index("def candidate_messages"):]

SERVER_PIPELINE = _SERVER_PROMPTS + r'''IMPROVED_RETRIEVER = build_retriever(RAG_ROWS)
VALID_PROVISION_IDS = set(IMPROVED_RETRIEVER['index'])

import subprocess
import sys
import time
import urllib.error
import urllib.request

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 8000
SERVER_ROOT = f'http://{SERVER_HOST}:{SERVER_PORT}'
SERVER_API = SERVER_ROOT + '/v1'
SERVER_API_KEY = 'legalai-local-colab'
BASE_SERVED_NAME = 'legalai-base'
LORA_SERVED_NAME = 'legal-complaint-lora'
SERVER_LOG = LOCAL_ROOT / 'vllm_server.log'
WARM_PIPELINE_FINGERPRINT = 'grounded_clean_output_2026_09_27'
COMPATIBLE_GENERATION_FINGERPRINTS = {'grounded_compact_assessment_2026_09_27'}
TRIAGE_PARAMS = 140
ASSESS_PARAMS = 220

''' + _SERVER_PARSE_JSON + r'''

def http_json(url, payload=None, timeout=30):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        url, data=data,
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Bearer ' + SERVER_API_KEY},
        method='GET' if payload is None else 'POST')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8')
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        body = error.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'vLLM HTTP {error.code}: {body}') from error

def server_log_tail(lines=100):
    if not SERVER_LOG.is_file():
        return '(server log has not been created)'
    return '\n'.join(SERVER_LOG.read_text(
        encoding='utf-8', errors='replace').splitlines()[-lines:])

def server_failure_report():
    if not SERVER_LOG.is_file():
        return '(server log has not been created)'
    text = SERVER_LOG.read_text(encoding='utf-8', errors='replace')
    marker = 'EngineCore failed to start.'
    position = text.rfind(marker)
    if position >= 0:
        return text[position:][-30000:]
    return '\n'.join(text.splitlines()[-300:])

def server_ready():
    try:
        with urllib.request.urlopen(SERVER_ROOT + '/health', timeout=3) as response:
            return response.status == 200
    except Exception:
        return False

def start_vllm_server():
    global SERVER_PROCESS, SERVER_LOG_HANDLE
    if server_ready():
        models = http_json(SERVER_API + '/models').get('data', [])
        names = {item.get('id') for item in models}
        required = {BASE_SERVED_NAME, LORA_SERVED_NAME}
        if required.issubset(names):
            print('Reusing healthy local vLLM server:', sorted(names))
            SERVER_PROCESS = None
            SERVER_LOG_HANDLE = None
            return
        raise RuntimeError('Port 8000 has a different server: ' + repr(sorted(names)))

    executable = shutil.which('vllm')
    if not executable:
        raise FileNotFoundError('vllm executable was not installed')
    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    SERVER_LOG_HANDLE = SERVER_LOG.open('w', encoding='utf-8', buffering=1)
    command = [
        executable, 'serve', BASE_MODEL,
        '--revision', BASE_REVISION,
        '--dtype', 'float16',
        '--max-model-len', '4096',
        '--max-num-seqs', '4',
        '--gpu-memory-utilization', '0.80',
        '--enforce-eager',
        '--enable-prefix-caching',
        '--enable-lora',
        '--max-lora-rank', str(adapter_config['r']),
        '--lora-modules', f'{LORA_SERVED_NAME}={ADAPTER_PATH}',
        '--served-model-name', BASE_SERVED_NAME,
        '--host', SERVER_HOST,
        '--port', str(SERVER_PORT),
        '--api-key', SERVER_API_KEY,
        '--disable-uvicorn-access-log',
    ]
    environment = os.environ.copy()
    environment['PYTHONUNBUFFERED'] = '1'
    try:
        from google.colab import userdata
        token = userdata.get('HF_TOKEN')
        if token:
            environment['HF_TOKEN'] = token
    except Exception:
        pass
    print('Starting isolated vLLM server process...')
    print('Server log:', SERVER_LOG)
    SERVER_PROCESS = subprocess.Popen(
        command, stdout=SERVER_LOG_HANDLE, stderr=subprocess.STDOUT,
        env=environment, start_new_session=True)
    deadline = time.monotonic() + 1200
    next_update = time.monotonic() + 30
    while time.monotonic() < deadline:
        exit_code = SERVER_PROCESS.poll()
        if exit_code is not None:
            SERVER_LOG_HANDLE.flush()
            raise RuntimeError(
                f'vLLM server exited with code {exit_code}. Root failure:\n'
                f'{server_failure_report()}')
        if server_ready():
            models = http_json(SERVER_API + '/models').get('data', [])
            names = {item.get('id') for item in models}
            required = {BASE_SERVED_NAME, LORA_SERVED_NAME}
            if not required.issubset(names):
                raise RuntimeError('Server started without required models: ' + repr(sorted(names)))
            print('vLLM server ready:', sorted(names))
            return
        if time.monotonic() >= next_update:
            print('Still starting vLLM... latest log line:')
            print(server_log_tail(1))
            next_update += 30
        time.sleep(2)
    raise TimeoutError(
        'vLLM did not become healthy within 20 minutes. Root failure:\n' +
        server_failure_report())

start_vllm_server()

def chat(messages, max_new_tokens, use_lora, response_format=None):
    payload = {
        'model': LORA_SERVED_NAME if use_lora else BASE_SERVED_NAME,
        'messages': messages,
        'temperature': 0.0,
        'max_tokens': max_new_tokens,
        'stream': False,
    }
    if response_format is not None:
        payload['response_format'] = response_format
    started = time.perf_counter()
    response = http_json(SERVER_API + '/chat/completions', payload, timeout=600)
    elapsed = time.perf_counter() - started
    text = response['choices'][0]['message']['content'].strip()
    completion_tokens = int(response.get('usage', {}).get('completion_tokens') or 0)
    return text, elapsed, completion_tokens

''' + _SERVER_FUNCTIONS


BENCHMARK = r'''MAX_BENCHMARK_CASES = 150  # @param {type:"integer"}
RESTART_WARM_BENCHMARK = False  # @param {type:"boolean"}

PREDICTIONS_PATH = PROJECT / 'warm_vllm_predictions.json'
REPORT_PATH = PROJECT / 'warm_vllm_report.json'
selected_inputs = BENCHMARK_INPUTS[:max(1, min(MAX_BENCHMARK_CASES, len(BENCHMARK_INPUTS)))]

def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)

predictions = []
if PREDICTIONS_PATH.is_file() and not RESTART_WARM_BENCHMARK:
    old = json.loads(PREDICTIONS_PATH.read_text(encoding='utf-8'))
    if old.get('adapter_sha256') != ADAPTER_SHA256 or old.get('base_revision') != BASE_REVISION:
        raise RuntimeError('Existing warm results use another model or adapter.')
    old_fingerprint = old.get('pipeline_fingerprint')
    if old_fingerprint == WARM_PIPELINE_FINGERPRINT:
        predictions = old.get('predictions', [])
        print('Resuming:', len(predictions), '/', len(selected_inputs))
    elif old_fingerprint in COMPATIBLE_GENERATION_FINGERPRINTS:
        previous = PROJECT / 'warm_vllm_previous_predictions.json'
        shutil.copy2(PREDICTIONS_PATH, previous)
        for row in old.get('predictions', []):
            assessments = row.get('candidate_assessments', [])
            retrieval = {'offence_candidates': assessments}
            final, actions, validation = assemble(
                row['complaint'], retrieval, assessments, row.get('triage', {}))
            predictions.append({
                **row,
                'evidence_gate_actions': actions,
                'final_output': final,
                'final_validation': validation,
                'output_cleaner_migrated': True,
            })
        print('Reprocessed saved model decisions with the tested output cleaner:',
              len(predictions), '/', len(selected_inputs))
        print('No repeated GPU generation was needed.')
    else:
        previous = PROJECT / 'warm_vllm_previous_predictions.json'
        shutil.copy2(PREDICTIONS_PATH, previous)
        print('Pipeline changed. Preserved earlier predictions at:', previous)
        print('Starting the corrected benchmark from case 1.')
elif RESTART_WARM_BENCHMARK:
    PREDICTIONS_PATH.unlink(missing_ok=True)

done = {row['case_id'] for row in predictions}
for index, case in enumerate(selected_inputs, 1):
    if case['case_id'] in done:
        continue
    result = run_warm_query(case['complaint'])
    record = {**case, **result}
    predictions.append(record)
    payload = {
        'schema_version': 1,
        'purpose': 'warm_query_latency_and_quality_regression',
        'engine': 'vllm',
        'base_model': BASE_MODEL,
        'base_revision': BASE_REVISION,
        'adapter_sha256': ADAPTER_SHA256,
        'pipeline_fingerprint': WARM_PIPELINE_FINGERPRINT,
        'warmup_excluded': True,
        'completed_cases': len(predictions),
        'target_cases': len(selected_inputs),
        'predictions': predictions,
    }
    atomic_json(PREDICTIONS_PATH, payload)
    print(f"{case['case_id']} ({index}/{len(selected_inputs)})",
          json.dumps(result['final_output'], ensure_ascii=False),
          f"{result['timing']['total_seconds']:.2f}s")

# Migration can finish all cases without entering the generation loop. Always
# persist the active pipeline fingerprint and reassembled final outputs.
atomic_json(PREDICTIONS_PATH, {
    'schema_version': 1,
    'purpose': 'warm_query_latency_and_quality_regression',
    'engine': 'vllm',
    'base_model': BASE_MODEL,
    'base_revision': BASE_REVISION,
    'adapter_sha256': ADAPTER_SHA256,
    'pipeline_fingerprint': WARM_PIPELINE_FINGERPRINT,
    'warmup_excluded': True,
    'completed_cases': len(predictions),
    'target_cases': len(selected_inputs),
    'predictions': predictions,
})

def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position); upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

def score(rows):
    tp = fp = fn = outcome_hits = exact_hits = positive = exact_positive = invalid = 0
    acceptable_hits = acceptable_positive = 0
    out_total = out_fp = 0
    for row in rows:
        gold = GOLD_BY_ID[row['case_id']]
        output = row['final_output']
        predicted = set(output.get('possible_provision_ids', []))
        required = set(gold['required_provision_ids'])
        optional = set(gold.get('optional_provision_ids', []))
        outcome_ok = output.get('outcome') == gold['outcome']
        strict = outcome_ok and predicted == required
        acceptable = outcome_ok and required.issubset(predicted) and predicted.issubset(required | optional)
        outcome_hits += int(outcome_ok); exact_hits += int(strict)
        acceptable_hits += int(acceptable)
        if gold['outcome'] == 'provision_match':
            positive += 1; exact_positive += int(strict)
            acceptable_positive += int(acceptable)
            tp += len(predicted & required); fp += len(predicted - required); fn += len(required - predicted)
        if gold['outcome'] == 'out_of_scope':
            out_total += 1
            out_fp += int(output.get('outcome') == 'provision_match' or bool(predicted))
        invalid += len(predicted - VALID_PROVISION_IDS)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        'cases': len(rows),
        'outcome_accuracy': outcome_hits / len(rows),
        'strict_exact_all_case_accuracy': exact_hits / len(rows),
        'strict_exact_positive_section_accuracy': exact_positive / positive if positive else 1.0,
        'answer_key_acceptable_all_case_accuracy': acceptable_hits / len(rows),
        'answer_key_acceptable_positive_section_accuracy': acceptable_positive / positive if positive else 1.0,
        'strict_section_precision': precision,
        'required_section_recall': recall,
        'strict_section_f1': 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        'out_of_scope_false_positive_rate': out_fp / out_total if out_total else 0.0,
        'invalid_provision_id_count': invalid,
    }

if len(predictions) == len(selected_inputs):
    totals = [row['timing']['total_seconds'] for row in predictions]
    metrics = score(predictions)
    latency = {
        'warmup_excluded': True,
        'minimum_seconds': min(totals),
        'median_seconds': statistics.median(totals),
        'p95_seconds': percentile(totals, 0.95),
        'maximum_seconds': max(totals),
        'mean_seconds': statistics.mean(totals),
        'repair_rate': sum(row['repair_used'] for row in predictions) / len(predictions),
    }
    baseline = {
        'outcome_accuracy': 0.92,
        'strict_exact_all_case_accuracy': 0.7066666666666667,
        'strict_exact_positive_section_accuracy': 0.62,
        'strict_section_precision': 0.8015267175572519,
        'required_section_recall': 0.8333333333333334,
        'out_of_scope_false_positive_rate': 0.0,
        'invalid_provision_id_count': 0,
    }
    comparable = len(predictions) == 150
    gates = {
        'full_150_case_comparison': comparable,
        'output_structure_100_percent': all(row['final_validation']['valid'] for row in predictions),
        'invalid_provision_ids_not_worse': metrics['invalid_provision_id_count'] <= baseline['invalid_provision_id_count'],
        'outcome_accuracy_not_worse': metrics['outcome_accuracy'] >= baseline['outcome_accuracy'],
        'exact_all_case_accuracy_not_worse': metrics['strict_exact_all_case_accuracy'] >= baseline['strict_exact_all_case_accuracy'],
        'exact_positive_accuracy_not_worse': metrics['strict_exact_positive_section_accuracy'] >= baseline['strict_exact_positive_section_accuracy'],
        'precision_not_worse': metrics['strict_section_precision'] >= baseline['strict_section_precision'],
        'recall_not_worse': metrics['required_section_recall'] >= baseline['required_section_recall'],
        'out_of_scope_false_positive_not_worse': metrics['out_of_scope_false_positive_rate'] <= baseline['out_of_scope_false_positive_rate'],
    }
    report = {
        'schema_version': 1,
        'purpose': 'warm_vllm_quality_and_latency_gate',
        'engine': 'vllm',
        'model': BASE_MODEL,
        'base_revision': BASE_REVISION,
        'adapter_sha256': ADAPTER_SHA256,
        'pipeline_fingerprint': WARM_PIPELINE_FINGERPRINT,
        'metrics': metrics,
        'warm_latency': latency,
        'established_rag_v2_2_baseline': baseline,
        'quality_gates': gates,
        'quality_preserved_against_established_baseline': comparable and all(gates.values()),
        'note': 'Regression labels are AI-reviewed research labels, not lawyer-verified accuracy.',
    }
    atomic_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('Saved:', REPORT_PATH)
else:
    print('Incomplete:', len(predictions), '/', len(selected_inputs))
'''


INTERACTIVE = r'''import ipywidgets as widgets
from IPython.display import display, clear_output, JSON as DisplayJSON

complaint_box = widgets.Textarea(
    placeholder='Describe the complaint in English, Hindi or Hinglish...',
    description='Complaint:', layout=widgets.Layout(width='100%', height='130px'),
    style={'description_width': '90px'})
run_button = widgets.Button(description='Run warm production query', button_style='primary')
query_output = widgets.Output()

def run_clicked(_):
    with query_output:
        clear_output()
        complaint = complaint_box.value.strip()
        if not complaint:
            print('Enter a complaint first.'); return
        result = run_warm_query(complaint)
        display(DisplayJSON(result['final_output'], expanded=True))
        print('Warm latency:', round(result['timing']['total_seconds'], 3), 'seconds')
        print('Triage:', round(result['timing']['triage_seconds'], 3), 'seconds')
        print('Retrieval:', round(result['timing']['retrieval_seconds'], 6), 'seconds')
        print('Assessment:', round(result['timing']['assessment_seconds'], 3), 'seconds')
        print('Repair used:', result['repair_used'])

run_button.on_click(run_clicked)
display(complaint_box, run_button, query_output)
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"gpuType": "T4", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": [
            md("""# Krishna LegalAI: warm production inference benchmark

This notebook measures **query 2 onward**. It launches vLLM as a separate local server process, loads the trained Qwen plus LoRA once, performs one excluded warm-up through both model paths, then records only warm latency. It preserves the trained adapter, six-candidate retrieval, statutory evidence checks and final section validation.

The engine is vLLM with automatic prefix caching. The notebook saves after every benchmark complaint and includes an interactive tester at the end.
"""),
            code(MOUNT),
            code(INSTALL),
            code(LOAD_DATA),
            code(CORE),
            code(SERVER_PIPELINE),
            code(BENCHMARK),
            code(INTERACTIVE),
            md("""## Start the backend API

Run this final cell after vLLM is ready. It starts the FastAPI service beside the already loaded model and performs a real smoke request. The API stores development sessions and drafts under `LegalAI/app_data` in Drive.
"""),
            code(BACKEND_API),
            md("""## Create a temporary HTTPS test endpoint

Run this only for supervised development testing. It downloads the official `cloudflared` client, creates a temporary Quick Tunnel, verifies token protection, tests separate users and sessions, exercises the complaint-draft flow, and sends four simultaneous model requests. The endpoint ends when this runtime stops.
"""),
            code(TUNNEL_API),
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
