"""Resumable QLoRA training and held-out evaluation for the Colab notebook.

This module is bundled into colab_training_input_v5.zip. It never reads the
sealed test until both candidate runs have completed their development scores.
"""
from __future__ import annotations

import gc
import hashlib
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

from transformers import TrainerCallback


MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
MODEL_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
TEMPLATE_NAME = "qwen3_instruct_2507_assistant_mask.jinja"
DATA_PREP_VERSION = "assistant-masked-left-truncate-v1"
EVAL_VERSION = "explicit_attention_mask_v1"
VARIANTS = ("complaint_only", "complaint_plus_bns_it_qa")
TRAIN_CONFIG = {"epochs": 2, "max_length": 1024, "learning_rate": 1e-4,
                "batch_size": 1, "gradient_accumulation": 8, "save_steps": 50,
                "lora_rank": 16, "lora_alpha": 32, "seed": 42}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def atomic_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def verify_input(input_dir: Path) -> dict:
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files_sha256"].items():
        if sha(input_dir / name) != digest:
            raise ValueError(f"Input SHA-256 mismatch: {name}")
    if manifest["counts"] != {"complaint_train": 4538, "complaint_plus_qa_train": 5525,
                              "development": 326, "sealed_test": 90,
                              "law_offences": 297, "live_recommendable": 19}:
        raise ValueError("Unexpected frozen dataset counts")
    return manifest


def run_fingerprint(input_dir: Path, variant: str) -> str:
    variant_manifest = input_dir / variant / "manifest.json"
    payload = {"model": MODEL_ID, "model_revision": MODEL_REVISION, "variant": variant,
               "variant_manifest_sha256": sha(variant_manifest), "config": TRAIN_CONFIG,
               "template_sha256": sha(input_dir / TEMPLATE_NAME),
               "data_prep_version": DATA_PREP_VERSION}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def checkpoint_complete(folder: Path) -> None:
    required = ("trainer_state.json", "optimizer.pt", "scheduler.pt")
    absent = [name for name in required if not (folder / name).is_file()]
    if not list(folder.glob("rng_state*.pth")):
        absent.append("rng_state*.pth")
    if not (folder / "adapter_model.safetensors").is_file() and not (folder / "adapter_model.bin").is_file():
        absent.append("adapter_model")
    if not (folder / "adapter_config.json").is_file():
        absent.append("adapter_config.json")
    if absent:
        raise ValueError(f"Checkpoint lacks resumable state: {absent}")


def archive_folder(folder: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED, allowZip64=True) as out:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                out.write(path, folder.name + "/" + path.relative_to(folder).as_posix())
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None:
            raise ValueError("Local checkpoint archive failed CRC check")


def publish_checkpoint(checkpoint: Path, drive_run: Path, fingerprint: str) -> None:
    checkpoint_complete(checkpoint)
    drive_run.mkdir(parents=True, exist_ok=True)
    name = checkpoint.name
    local_zip = checkpoint.parent / f"{name}.zip"
    archive_folder(checkpoint, local_zip)
    digest = sha(local_zip)
    dest = drive_run / f"{name}.zip"
    temp = drive_run / f"{name}.zip.part"
    shutil.copyfile(local_zip, temp)
    if sha(temp) != digest:
        raise ValueError("Drive checkpoint copy checksum mismatch")
    os.replace(temp, dest)
    atomic_json(drive_run / f"{name}.json", {"step": int(name.split("-")[-1]),
                "zip": dest.name, "sha256": digest, "bytes": dest.stat().st_size,
                "run_fingerprint": fingerprint, "complete": True})
    local_zip.unlink(missing_ok=True)
    complete = sorted(drive_run.glob("checkpoint-*.json"),
                      key=lambda p: int(p.stem.split("-")[-1]), reverse=True)
    for old in complete[2:]:
        try:
            old_data = json.loads(old.read_text(encoding="utf-8"))
            (drive_run / old_data["zip"]).unlink(missing_ok=True)
            old.unlink(missing_ok=True)
        except Exception:
            pass  # Retention cleanup must not invalidate the new checkpoint.


def restore_latest(drive_run: Path, local_output: Path, fingerprint: str) -> Path | None:
    if not drive_run.exists():
        return None
    markers = sorted(drive_run.glob("checkpoint-*.json"),
                     key=lambda p: int(p.stem.split("-")[-1]), reverse=True)
    for marker in markers:
        try:
            meta = json.loads(marker.read_text(encoding="utf-8"))
            if not meta.get("complete") or meta["run_fingerprint"] != fingerprint:
                continue
            source = drive_run / meta["zip"]
            if source.stat().st_size != meta["bytes"] or sha(source) != meta["sha256"]:
                continue
            local_output.mkdir(parents=True, exist_ok=True)
            local_zip = local_output / source.name
            shutil.copyfile(source, local_zip)
            if sha(local_zip) != meta["sha256"]:
                raise ValueError("Downloaded checkpoint hash mismatch")
            folder_name = source.name.removesuffix(".zip")
            with zipfile.ZipFile(local_zip) as archive:
                if archive.testzip() is not None:
                    raise ValueError("Checkpoint CRC mismatch")
                if any(not name.startswith(folder_name + "/") or ".." in Path(name).parts
                       for name in archive.namelist()):
                    raise ValueError("Unsafe checkpoint archive path")
                archive.extractall(local_output)
            local_zip.unlink(missing_ok=True)
            checkpoint = local_output / folder_name
            checkpoint_complete(checkpoint)
            print(f"Resuming from verified Drive checkpoint: {folder_name}")
            return checkpoint
        except Exception as exc:
            print(f"Ignoring incomplete checkpoint {marker.name}: {exc}")
    return None


class DriveBackupCallback(TrainerCallback):
    def __init__(self, drive_run: Path, fingerprint: str):
        self.drive_run = drive_run
        self.fingerprint = fingerprint

    def on_save(self, args, state, control, **kwargs):
        checkpoint = Path(args.output_dir) / f"checkpoint-{state.global_step}"
        publish_checkpoint(checkpoint, self.drive_run, self.fingerprint)
        print(f"Drive backup complete at step {state.global_step}")
        return control


def load_model(tokenizer=None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    if not torch.cuda.is_available():
        raise RuntimeError("Colab GPU is not active. Runtime > Change runtime type > GPU.")
    free, total = torch.cuda.mem_get_info()
    if total < 13 * 1024**3:
        raise RuntimeError(f"GPU has {total / 1024**3:.1f} GB VRAM; this 4B training profile needs about 13 GB.")
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    if tokenizer is None:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION, use_fast=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                              bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, device_map="auto", quantization_config=quant,
        dtype=dtype)
    model.config.use_cache = False
    return model, tokenizer, dtype


def prepare_training_data(input_dir: Path, variant: str):
    """Mask non-assistant tokens and keep the answer when a prompt is long."""
    from datasets import Dataset
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION, use_fast=True)
    original_template = tokenizer.chat_template
    patched_template = (input_dir / TEMPLATE_NAME).read_text(encoding="utf-8")
    if "generation %}" not in patched_template or "endgeneration %}" not in patched_template:
        raise ValueError("Training template lacks assistant generation markers")
    tokenizer.chat_template = patched_template
    data = read_jsonl(input_dir / variant / "train_sft.jsonl")
    expected = 4538 if variant == "complaint_only" else 5525
    if len(data) != expected:
        raise ValueError("Training data count mismatch")
    processed = []
    dropped = 0
    clipped = 0
    for index, row in enumerate(data):
        messages = row["messages"]
        if tokenizer.apply_chat_template(messages, chat_template=original_template, tokenize=False) != \
                tokenizer.apply_chat_template(messages, tokenize=False):
            raise ValueError(f"Assistant mask template changes model input at row {index}")
        encoded = tokenizer.apply_chat_template(messages, tokenize=True, return_dict=True,
                                                return_assistant_tokens_mask=True)
        ids = encoded["input_ids"]
        mask = encoded["assistant_masks"]
        if len(ids) != len(mask) or not any(mask):
            raise ValueError(f"Missing assistant tokens at row {index}")
        if sum(mask) > TRAIN_CONFIG["max_length"]:
            dropped += 1  # The answer itself cannot fit; do not train on a fragment.
            continue
        if len(ids) > TRAIN_CONFIG["max_length"]:
            ids = ids[-TRAIN_CONFIG["max_length"]:]
            mask = mask[-TRAIN_CONFIG["max_length"]:]
            clipped += 1  # Preserve the answer and most recent context.
        labels = [token if included else -100 for token, included in zip(ids, mask, strict=True)]
        if not any(label != -100 for label in labels):
            raise ValueError(f"No trainable answer tokens after clipping row {index}")
        processed.append({"input_ids": ids, "labels": labels})
    print(f"{variant}: {len(processed)} trainable rows; {clipped} long prompts clipped; "
          f"{dropped} overlong answers excluded")
    return tokenizer, Dataset.from_list(processed)


def trainer_for(input_dir: Path, variant: str, output_dir: Path, drive_run: Path,
                fingerprint: str, gradient_checkpointing: bool):
    import torch
    from peft import LoraConfig, prepare_model_for_kbit_training
    from trl import SFTConfig, SFTTrainer
    tokenizer, train_dataset = prepare_training_data(input_dir, variant)
    model, tokenizer, dtype = load_model(tokenizer)
    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=gradient_checkpointing)
    config = SFTConfig(
        output_dir=str(output_dir), num_train_epochs=TRAIN_CONFIG["epochs"],
        learning_rate=TRAIN_CONFIG["learning_rate"],
        per_device_train_batch_size=TRAIN_CONFIG["batch_size"],
        gradient_accumulation_steps=TRAIN_CONFIG["gradient_accumulation"],
        max_length=TRAIN_CONFIG["max_length"], assistant_only_loss=False,
        packing=False, gradient_checkpointing=gradient_checkpointing,
        optim="paged_adamw_8bit",
        bf16=dtype == torch.bfloat16, fp16=dtype == torch.float16,
        save_strategy="steps", save_steps=TRAIN_CONFIG["save_steps"],
        save_total_limit=2, save_only_model=False, logging_steps=10,
        eval_strategy="no", warmup_ratio=0.03, lr_scheduler_type="cosine",
        report_to="none", seed=TRAIN_CONFIG["seed"],
        dataloader_num_workers=0)
    lora = LoraConfig(r=TRAIN_CONFIG["lora_rank"], lora_alpha=TRAIN_CONFIG["lora_alpha"],
                      lora_dropout=0.05, target_modules="all-linear", task_type="CAUSAL_LM")
    trainer = SFTTrainer(model=model, args=config, train_dataset=train_dataset,
                         processing_class=tokenizer, peft_config=lora,
                         callbacks=[DriveBackupCallback(drive_run, fingerprint)])
    return trainer, tokenizer


def export_adapter(trainer, tokenizer, drive_run: Path, fingerprint: str) -> None:
    local = Path(trainer.args.output_dir) / "final_adapter"
    trainer.save_model(str(local))
    tokenizer.save_pretrained(str(local))
    if not (local / "adapter_model.safetensors").exists():
        raise ValueError("Final LoRA adapter was not saved")
    local_zip = local.parent / "final_adapter.zip"
    archive_folder(local, local_zip)
    temp = drive_run / "final_adapter.zip.part"
    shutil.copyfile(local_zip, temp)
    digest = sha(local_zip)
    if sha(temp) != digest:
        raise ValueError("Final adapter copy mismatch")
    os.replace(temp, drive_run / "final_adapter.zip")
    atomic_json(drive_run / "training_complete.json", {
        "run_fingerprint": fingerprint, "adapter_sha256": digest,
        "adapter_bytes": (drive_run / "final_adapter.zip").stat().st_size,
        "global_step": trainer.state.global_step, "epochs": TRAIN_CONFIG["epochs"],
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION})


def training_finished(drive_run: Path, fingerprint: str) -> bool:
    marker = drive_run / "training_complete.json"
    archive = drive_run / "final_adapter.zip"
    if not marker.exists() or not archive.exists():
        return False
    data = json.loads(marker.read_text(encoding="utf-8"))
    return data.get("run_fingerprint") == fingerprint and data.get("adapter_sha256") == sha(archive)


def train_variant(input_dir: Path, drive_root: Path, local_root: Path, variant: str) -> None:
    import torch

    fingerprint = run_fingerprint(input_dir, variant)
    drive_run = drive_root / "runs" / variant
    if training_finished(drive_run, fingerprint):
        print(f"Training already completed: {variant}")
        return
    local_output = local_root / variant

    def attempt(gradient_checkpointing: bool) -> None:
        checkpoint = restore_latest(drive_run, local_output, fingerprint)
        trainer, tokenizer = trainer_for(input_dir, variant, local_output, drive_run,
                                         fingerprint, gradient_checkpointing)
        try:
            mode = "memory-saving" if gradient_checkpointing else "faster"
            print(f"Training {variant} in {mode} mode")
            trainer.train(resume_from_checkpoint=str(checkpoint) if checkpoint else None)
            export_adapter(trainer, tokenizer, drive_run, fingerprint)
        finally:
            del trainer, tokenizer
            gc.collect()
            torch.cuda.empty_cache()

    fallback = False
    try:
        attempt(gradient_checkpointing=False)
    except RuntimeError as exc:
        if not isinstance(exc, torch.cuda.OutOfMemoryError) and "out of memory" not in str(exc).lower():
            raise
        fallback = True
    if fallback:
        gc.collect()
        torch.cuda.empty_cache()
        print("GPU ran out of memory in faster mode; retrying from the latest Drive checkpoint "
              "with gradient checkpointing enabled.")
        attempt(gradient_checkpointing=True)
    print(f"Training complete: {variant}")


def load_adapter(drive_run: Path, local_root: Path):
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer
    model, tokenizer, _ = load_model()
    source = drive_run / "final_adapter.zip"
    local_zip = local_root / (drive_run.name + "_adapter.zip")
    shutil.copyfile(source, local_zip)
    if sha(local_zip) != json.loads((drive_run / "training_complete.json").read_text()) ["adapter_sha256"]:
        raise ValueError("Adapter download mismatch")
    target = local_root / (drive_run.name + "_adapter")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(local_zip) as archive:
        if archive.testzip() is not None:
            raise ValueError("Adapter ZIP CRC mismatch")
        archive.extractall(target)
    model = PeftModel.from_pretrained(model, target / "final_adapter")
    model.config.use_cache = True
    model.eval()
    return model, tokenizer


def parse_json(text: str) -> dict | None:
    start = text.find("{")
    if start < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def score(rows: list[dict], predictions: list[dict], valid_ids: set[str]) -> dict:
    matched = 0
    outcome = 0
    exact_sections = 0
    parsed = 0
    invalid = 0
    for row, pred in zip(rows, predictions, strict=True):
        expected = json.loads(row["messages"][-1]["content"])
        if "outcome" not in expected:
            continue  # Workflow cases are evaluated separately from triage.
        matched += 1
        answer = pred.get("parsed")
        if not isinstance(answer, dict):
            continue
        parsed += 1
        outcome += answer.get("outcome") == expected["outcome"]
        given = answer.get("possible_provision_ids", [])
        if not isinstance(given, list):
            given = []
        exact_sections += set(given) == set(expected.get("possible_provision_ids", []))
        invalid += sum(pid not in valid_ids for pid in given)
    return {"triage_cases": matched, "json_parse_rate": parsed / matched,
            "outcome_accuracy": outcome / matched,
            "exact_section_set_accuracy": exact_sections / matched,
            "invalid_provision_ids": invalid,
            "selection_score": (outcome + exact_sections) / (2 * matched)}


def evaluate(input_dir: Path, drive_root: Path, local_root: Path, variant: str,
             split: str, valid_ids: set[str]) -> dict:
    import torch
    drive_run = drive_root / "runs" / variant
    file = "dev_sft.jsonl" if split == "dev" else "evaluation/sealed_test.jsonl"
    data = read_jsonl(input_dir / variant / file) if split == "dev" else read_jsonl(input_dir / file)
    out = drive_run / f"{split}_predictions.jsonl"
    metrics_file = drive_run / f"{split}_metrics.json"
    predictions = read_jsonl(out) if out.exists() else []
    current_predictions = (len(predictions) <= len(data) and
                           all(pred.get("generation_version") == EVAL_VERSION and
                               pred.get("index") == index
                               for index, pred in enumerate(predictions)))
    if not current_predictions:
        print(f"Discarding old {variant} {split} predictions; evaluation method changed")
        predictions = []
    if metrics_file.exists() and len(predictions) == len(data):
        metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
        if metrics.get("generation_version") == EVAL_VERSION:
            return metrics
    if len(predictions) > len(data):
        raise ValueError("Prediction file is longer than evaluation set")
    model, tokenizer = load_adapter(drive_run, local_root)
    for index in range(len(predictions), len(data)):
        row = data[index]
        messages = row["messages"][:-1]
        input_ids = tokenizer.apply_chat_template(messages, add_generation_prompt=True,
                                                   return_tensors="pt").to(model.device)
        attention_mask = torch.ones_like(input_ids, dtype=torch.long)
        with torch.inference_mode():
            result = model.generate(input_ids=input_ids, attention_mask=attention_mask,
                                    max_new_tokens=180, do_sample=False,
                                    pad_token_id=tokenizer.eos_token_id)
        response = tokenizer.decode(result[0, input_ids.shape[-1]:], skip_special_tokens=True)
        predictions.append({"index": index, "text": response, "parsed": parse_json(response),
                            "generation_version": EVAL_VERSION})
        if (index + 1) % 10 == 0 or index + 1 == len(data):
            temp = out.with_suffix(".jsonl.part")
            temp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in predictions),
                            encoding="utf-8")
            os.replace(temp, out)
            print(f"{variant} {split}: {index + 1}/{len(data)} saved")
    metrics = score(data, predictions, valid_ids)
    metrics["generation_version"] = EVAL_VERSION
    atomic_json(metrics_file, metrics)
    del model, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    return metrics


def run(input_dir: Path, drive_root: Path) -> dict:
    verify_input(input_dir)
    local_root = Path("/content/legal_ai_work")
    local_root.mkdir(parents=True, exist_ok=True)
    catalogue = json.loads((input_dir / "evaluation" / "offence_catalogue.json").read_text(encoding="utf-8"))
    valid_ids = {row["provision_id"] for row in catalogue}
    if len(valid_ids) != 297:
        raise ValueError("Offence catalogue mismatch")
    results = {}
    for variant in VARIANTS:
        train_variant(input_dir, drive_root, local_root, variant)
        results[variant] = evaluate(input_dir, drive_root, local_root, variant, "dev", valid_ids)
    chosen = max(VARIANTS, key=lambda variant: results[variant]["selection_score"])
    atomic_json(drive_root / "model_selection.json", {"chosen": chosen, "development": results,
                "rule": "Highest mean of development outcome and exact-section-set accuracy; tie favors complaint_only."})
    sealed = evaluate(input_dir, drive_root, local_root, chosen, "sealed", valid_ids)
    summary = {"chosen": chosen, "development": results, "sealed": sealed,
               "adapter": f"runs/{chosen}/final_adapter.zip", "base_model": MODEL_ID,
               "base_revision": MODEL_REVISION,
               "note": "Scores measure agreement with AI-reviewed research labels, not lawyer-verified accuracy."}
    atomic_json(drive_root / "training_results.json", summary)
    print(json.dumps(summary, indent=2))
    return summary
