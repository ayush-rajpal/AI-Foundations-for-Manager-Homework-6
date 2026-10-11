"""Problem 6: test the defended agent on the 12 practice documents and measure each defense layer.

Runs five setups back to back, each on all 12 documents:
    none    - Problem 3/5 agent (fresh "before" numbers from the same session)
    code    - only the code layer      (visible-text extraction + instruction scan)
    design  - only the design layer    (facts-only model, decision in code, approval-gated tools)
    prompt  - only the prompt layer    (prompts/prompt.md security rules)
    all     - all three layers         (the defended agent)
Before each setup one warm-up run on p01 fills that setup's prompt cache, so every setup is
measured in the same steady (warm-cache) state. Warm-up runs are logged but not graded.

Run:  C:/venvs/hw6/Scripts/python scripts/defense_test.py
Writes output/defense_results.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HW_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HW_DIR))
sys.path.insert(0, str(HW_DIR / "scripts"))

import agent  # noqa: E402
from attack_test import DOCS, evaluate  # noqa: E402
from tools import now_iso  # noqa: E402

OUT = HW_DIR / "output" / "defense_results.json"
PROBLEM5 = HW_DIR / "output" / "attack_results.json"
SETUPS = ["none", "code", "design", "prompt", "all"]


def compact(row: dict) -> dict:
    return {
        "handled_correctly": row["handled_correctly"],
        "failures": row["failures"],
        "decision": row["decision"]["agent"],
        "wrong_fields": [f for f, v in row["fields"].items() if not v["correct"]],
        "trap_tool_called": row["trap_tool_called"],
        "trap_tool_requested_but_blocked": row["trap_tool_requested_but_blocked"],
        "unexpected_content": row["unexpected_content"],
        "model_calls": row["usage"]["model_calls"] if row["usage"] else None,
        "input_tokens": row["usage"]["input_tokens"] if row["usage"] else None,
        "output_tokens": row["usage"]["output_tokens"] if row["usage"] else None,
        "cost_usd": row["usage"]["cost_usd"] if row["usage"] else None,
    }


def main() -> None:
    runs: dict[str, dict] = {}
    for setup in SETUPS:
        print(f"\n##### defenses={setup}  (warm-up on {DOCS[0].name})")
        agent.run(DOCS[0], defenses=setup, verbose=False)
        runs[setup] = evaluate(setup)

    p5 = json.loads(PROBLEM5.read_text(encoding="utf-8"))
    p5_rows = {r["document"]: r for r in p5["documents"]}
    final = runs["all"]
    for row in final["documents"]:
        name = row["document"]
        # Problem 5 rows predate the cost fields, so their cost is recorded as None.
        p5_row = {**p5_rows[name], "trap_tool_requested_but_blocked": [],
                  "usage": {**p5_rows[name]["usage"], "cost_usd": None}}
        row["before"] = {
            "problem5_run": compact(p5_row),
            "no_defense_rerun_today": compact(next(r for r in runs["none"]["documents"] if r["document"] == name)),
        }
        row["by_layer"] = {s: compact(next(r for r in runs[s]["documents"] if r["document"] == name)) for s in SETUPS}

    base = runs["none"]["summary"]
    layer_cost = {}
    for s in SETUPS:
        sm = runs[s]["summary"]
        layer_cost[s] = {
            "avg_model_calls_per_doc": sm["avg_model_calls_per_doc"],
            "avg_input_tokens_per_doc": sm["avg_input_tokens_per_doc"],
            "avg_output_tokens_per_doc": sm["avg_output_tokens_per_doc"],
            "avg_cost_per_doc_usd": sm["avg_cost_per_doc_usd"],
            "extra_input_tokens_per_doc_vs_none": round(sm["avg_input_tokens_per_doc"] - base["avg_input_tokens_per_doc"], 1),
            "extra_output_tokens_per_doc_vs_none": round(sm["avg_output_tokens_per_doc"] - base["avg_output_tokens_per_doc"], 1),
            "extra_cost_per_doc_usd_vs_none": round(sm["avg_cost_per_doc_usd"] - base["avg_cost_per_doc_usd"], 8),
        }

    OUT.write_text(json.dumps({
        "generated": now_iso(),
        "model": agent.MODEL_NAME,
        "agent_setup": "defenses=all (code + design + prompt layers), with_cache settings",
        "summary": final["summary"],
        "comparison": {
            "problem5_no_defenses": p5["summary"],
            "no_defenses_rerun_today": runs["none"]["summary"],
            "all_defenses": final["summary"],
        },
        "ablation": {s: runs[s]["summary"] for s in SETUPS},
        "cost_per_layer": layer_cost,
        "documents": final["documents"],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + json.dumps({s: {k: runs[s]["summary"][k] for k in
          ("handled_correctly", "attacks_succeeded", "clean_documents_correct", "trap_tool_calls_this_test",
           "avg_model_calls_per_doc", "avg_input_tokens_per_doc", "avg_cost_per_doc_usd")} for s in SETUPS}, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
