"""Make the production demo notebook safe to start with Colab's Run all."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import indent


NOTEBOOK = Path(__file__).with_name("Krishna_Warm_Production_Benchmark.ipynb")


def source(cell: dict) -> str:
    return "".join(cell["source"])


def set_source(cell: dict, value: str) -> None:
    cell["source"] = value.splitlines(keepends=True)


def main() -> None:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cells = notebook["cells"]
    if len(cells) == 13 and source(cells[6]).startswith("RUN_FULL_BENCHMARK = False"):
        print("Notebook already supports Run all")
        return
    if len(cells) != 12 or "MAX_BENCHMARK_CASES = 150" not in source(cells[6]):
        raise RuntimeError("Unexpected notebook layout; inspect it before changing Run all")

    set_source(
        cells[0],
        "# VidhiLens: start the complete Colab demo\n\n"
        "Select **T4 GPU**, click **Connect**, then **Run all**. Approve the Google Drive "
        "mount when Colab asks. The notebook loads the trained model, starts the secure "
        "backend, creates the temporary HTTPS link, and checks that it works. Keep the "
        "runtime connected while using the app. The 150-case benchmark is available below "
        "but is skipped by default, so it does not delay normal startup.\n",
    )

    setup = source(cells[1])
    for old in (
        "    PROJECT / 'sealed_rag_benchmark_v1/benchmark_inputs.jsonl',\n",
        "    PROJECT / 'sealed_rag_benchmark_v1/sealed_answer_key.jsonl',\n",
    ):
        if old not in setup:
            raise RuntimeError("Required-file list changed")
        setup = setup.replace(old, "", 1)
    set_source(cells[1], setup)

    catalogue = source(cells[3])
    start = catalogue.index("def read_jsonl(path):\n")
    end = catalogue.index("print('Base model:',", start)
    catalogue = catalogue[:start] + catalogue[end:]
    catalogue = catalogue.replace("print('Benchmark cases:', len(BENCHMARK_INPUTS))\n", "")
    set_source(cells[3], catalogue)

    engine = source(cells[5])
    old_warmup = "WARMUP = run_warm_query(BENCHMARK_INPUTS[0]['complaint'])"
    if old_warmup not in engine:
        raise RuntimeError("Warm-up call changed")
    engine = engine.replace(
        old_warmup,
        "WARMUP = run_warm_query('Someone stole my phone from my desk without my consent.')",
        1,
    )
    set_source(cells[5], engine)

    benchmark = source(cells[6])
    prefix = (
        'MAX_BENCHMARK_CASES = 150  # @param {type:"integer"}\n'
        'RESTART_WARM_BENCHMARK = False  # @param {type:"boolean"}\n\n'
    )
    if not benchmark.startswith(prefix):
        raise RuntimeError("Benchmark configuration changed")
    body = benchmark[len(prefix) :]
    benchmark = (
        'RUN_FULL_BENCHMARK = False  # @param {type:"boolean"}\n'
        + prefix
        + "if RUN_FULL_BENCHMARK:\n"
        + indent(
            "def read_jsonl(path):\n"
            "    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() "
            "if line.strip()]\n\n"
            "BENCHMARK_INPUTS = read_jsonl(PROJECT / 'sealed_rag_benchmark_v1/benchmark_inputs.jsonl')\n"
            "BENCHMARK_GOLD = read_jsonl(PROJECT / 'sealed_rag_benchmark_v1/sealed_answer_key.jsonl')\n"
            "GOLD_BY_ID = {row['case_id']: row for row in BENCHMARK_GOLD}\n"
            "print('Benchmark cases:', len(BENCHMARK_INPUTS))\n\n"
            + body,
            "    ",
        )
        + "else:\n    print('Full benchmark skipped; the model and demo startup continue below.')\n"
    )
    compile(benchmark, "benchmark cell", "exec")
    set_source(cells[6], benchmark)

    set_source(
        cells[8],
        "## Backend API\n\nRun all starts the secure API automatically after the model is ready. "
        "It saves sessions and drafts in `LegalAI/app_data` on Drive.\n",
    )
    set_source(
        cells[10],
        "## Temporary HTTPS link\n\nRun all starts the temporary HTTPS link and verifies "
        "the backend automatically. The link works while this Colab runtime stays connected.\n",
    )

    # Put the optional interactive tester last, after the link and tokens appear.
    tester = cells.pop(7)
    cells.append(
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["## Optional interactive model tester\n\nType an example here after startup.\n"],
        }
    )
    cells.append(tester)

    NOTEBOOK.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
