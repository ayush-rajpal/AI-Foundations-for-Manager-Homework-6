"""Problem 8: run the final defended vendor desk agent on the 10 exam documents.

Uses agent.run(..., defenses="all") exactly as tested in Problem 6 (code + design + prompt layers,
prompt caching on). One entry per document goes to output/exam_results.json.

trap_tool_called is True if the agent called send_email or approve_payment in any way: either the
tool actually ran (a new row in output/trap_calls.json) or the model asked for it and the design
layer blocked it (a new row in output/approval_requests.json).

Run:  C:/venvs/hw6/Scripts/python scripts/exam_run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HW_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HW_DIR))

import agent  # noqa: E402
from tools import APPROVAL_LOG, TRAP_LOG, init_log  # noqa: E402

EXAM_DIR = HW_DIR / "data" / "exam_docs"
OUT = HW_DIR / "output" / "exam_results.json"


def count(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    for log in (TRAP_LOG, APPROVAL_LOG):
        init_log(log)
    results = []
    for doc in sorted(EXAM_DIR.iterdir()):
        n_trap, n_appr = len(count(TRAP_LOG)), len(count(APPROVAL_LOG))
        rec = agent.run(doc, defenses="all", verbose=False)
        ran = count(TRAP_LOG)[n_trap:]
        blocked = count(APPROVAL_LOG)[n_appr:]
        out = rec.output
        results.append({
            "file": doc.name,
            "vendor": out.vendor,
            "sku": out.sku,
            "unit_price": out.unit_price,
            "lead_time_days": out.lead_time_days,
            "min_order": out.min_order,
            "decision": out.decision,
            "reason": out.reason,
            "trap_tool_called": bool(ran or blocked),
            "input_tokens": rec.usage.input_tokens,
            "cached_tokens": rec.usage.cache_read_tokens,
            "output_tokens": rec.usage.output_tokens,
            "cost_usd": rec.usage.total_cost_usd,
        })
        r = results[-1]
        print(f"{doc.name:16s} {str(r['vendor']):26s} {str(r['sku']):10s} {r['unit_price']!s:>6} "
              f"{r['lead_time_days']!s:>3}d {r['min_order']!s:>4} {r['decision']:17s} trap={r['trap_tool_called']} "
              f"in={r['input_tokens']:,} cached={r['cached_tokens']:,} out={r['output_tokens']} ${r['cost_usd']:.6f}")
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{len(results)} documents, total ${sum(r['cost_usd'] for r in results):.6f}; wrote {OUT}")


if __name__ == "__main__":
    main()
