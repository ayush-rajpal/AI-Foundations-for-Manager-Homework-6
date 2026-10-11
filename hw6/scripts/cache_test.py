"""Problem 4: run the agent on all 12 practice documents with and without prompt caching.

Every model call's token counts are taken from the raw `usage` block of the API's HTTP response
(captured with an httpx response hook), not estimated. Cost uses data/prices.json.

Run:  C:/venvs/hw6/Scripts/python scripts/cache_test.py
Writes output/cache_test.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx2 as httpx  # openai 3.x ships on httpx2
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

HW_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HW_DIR))

import agent  # noqa: E402  (loads .env, builds the agent)
from tools import now_iso  # noqa: E402

DOCS = sorted((HW_DIR / "data" / "practice_docs").iterdir())
KEY = {row["file"]: row for row in json.loads((HW_DIR / "data" / "practice_key.json").read_text())}
OUT = HW_DIR / "output" / "cache_test.json"
FACT_FIELDS = ("vendor", "sku", "unit_price", "lead_time_days", "min_order", "decision")

raw_responses: list[dict] = []  # every /responses body's id + usage, in call order


async def capture_usage(response: httpx.Response) -> None:
    if response.request.url.path.endswith("/responses"):
        await response.aread()
        body = response.json()
        raw_responses.append({
            "response_id": body.get("id"),
            "usage": body.get("usage"),
            "portkey_cache_status": response.headers.get("x-portkey-cache-status"),
            "provider": response.headers.get("x-portkey-provider"),
        })


def hooked_model() -> OpenAIResponsesModel:
    client = AsyncOpenAI(
        api_key=os.environ["PORTKEY_API_KEY"],
        base_url=os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1"),
        default_headers={"x-portkey-provider": "openai"},
        http_client=httpx.AsyncClient(event_hooks={"response": [capture_usage]}, timeout=120),
    )
    return OpenAIResponsesModel(agent.MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def call_record(setup: str, doc: str, call_index: int, raw: dict) -> dict:
    u = raw["usage"]
    in_details = u.get("input_tokens_details") or {}
    out_details = u.get("output_tokens_details") or {}
    cache_read = in_details.get("cached_tokens", 0) or 0
    cache_write = in_details.get("cache_write_tokens", 0) or 0
    cost = agent.cost_usd(u["input_tokens"], cache_read, cache_write, u["output_tokens"])
    return {
        "setup": setup,
        "document": doc,
        "call_index": call_index,
        "response_id": raw["response_id"],
        "portkey_cache_status": raw["portkey_cache_status"],  # REFRESH = real model call, HIT = replay
        "provider": raw["provider"],
        "api_usage": u,  # verbatim from the API
        "input_tokens": u["input_tokens"],
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "uncached_input_tokens": u["input_tokens"] - cache_read - cache_write,
        "output_tokens": u["output_tokens"],
        "reasoning_tokens": out_details.get("reasoning_tokens", 0),
        "total_tokens": u.get("total_tokens"),
        "cost_breakdown_usd": cost,
        "cost_usd": round(sum(cost.values()), 8),
    }


def totals(rows: list[dict]) -> dict:
    keys = ("input_tokens", "cache_read_tokens", "cache_write_tokens", "uncached_input_tokens",
            "output_tokens", "reasoning_tokens", "total_tokens")
    t = {k: sum(r[k] for r in rows) for k in keys}
    t["model_calls"] = len(rows)
    t["cost_usd"] = round(sum(r["cost_usd"] for r in rows), 8)
    for bucket in ("uncached_input", "cached_input", "cache_write", "output"):
        t[f"cost_{bucket}_usd"] = round(sum(r["cost_breakdown_usd"][bucket] for r in rows), 8)
    return t


def main() -> None:
    calls: list[dict] = []
    runs: list[dict] = []
    model = hooked_model()
    with agent.vendor_desk.override(model=model), agent.vendor_desk_no_cache.override(model=model):
        for setup in ("with_cache", "without_cache"):
            print(f"\n##### {setup}")
            for doc in DOCS:
                start = len(raw_responses)
                result = agent.run(doc, setup=setup, defenses="none", verbose=False)
                new = raw_responses[start:]
                rows = [call_record(setup, doc.name, i, raw) for i, raw in enumerate(new, 1)]
                calls.extend(rows)

                out = result.output.model_dump()
                key = KEY[doc.name]
                matches = {f: (out[f] == key[f]) for f in FACT_FIELDS}
                runs.append({
                    "setup": setup, "document": doc.name, "model_calls": len(rows),
                    **{k: v for k, v in totals(rows).items() if k != "model_calls"},
                    "output": out, "matches_key": matches, "all_correct": all(matches.values()),
                })
                print(
                    f"{doc.name:28s} calls={len(rows)} in={sum(r['input_tokens'] for r in rows):>6,} "
                    f"read={sum(r['cache_read_tokens'] for r in rows):>6,} "
                    f"write={sum(r['cache_write_tokens'] for r in rows):>6,} "
                    f"out={sum(r['output_tokens'] for r in rows):>4} "
                    f"${sum(r['cost_usd'] for r in rows):.6f} "
                    f"{'OK' if all(matches.values()) else 'MISMATCH ' + str([f for f, ok in matches.items() if not ok])}"
                )

    summary = {s: totals([c for c in calls if c["setup"] == s]) for s in ("with_cache", "without_cache")}
    for s in summary:
        summary[s]["documents"] = 12
        summary[s]["avg_cost_per_document_usd"] = round(summary[s]["cost_usd"] / 12, 8)
        summary[s]["documents_all_correct"] = sum(r["all_correct"] for r in runs if r["setup"] == s)

    # Verification: the no-cache setup must read zero cached tokens on every call, and no call may be
    # a Portkey response-cache replay (those carry old usage and never reach the model).
    leaked = [c for c in calls if c["setup"] == "without_cache" and c["cache_read_tokens"]]
    replays = [c for c in calls if c["portkey_cache_status"] == "HIT"]
    hits = [c for c in calls if c["setup"] == "with_cache" and c["cache_read_tokens"]]
    verification = {
        "without_cache_calls_reading_cached_tokens": len(leaked),
        "without_cache_calls_writing_cache": sum(1 for c in calls if c["setup"] == "without_cache" and c["cache_write_tokens"]),
        "without_cache_ok": not leaked,
        "portkey_replayed_calls": len(replays),
        "with_cache_calls_reading_from_cache": len(hits),
        "with_cache_calls_total": summary["with_cache"]["model_calls"],
        "providers": sorted({c["provider"] for c in calls if c["provider"]}),
    }

    OUT.write_text(json.dumps({
        "generated": now_iso(),
        "model": agent.MODEL_NAME,
        "prices_per_1m": agent.PRICES,
        "setups": {
            "with_cache": "openai_prompt_cache_key + prompt_cache_options mode=implicit + cache breakpoint after the instructions (prompt + handbook)",
            "without_cache": "prompt_cache_options mode=explicit, no breakpoints, AND a new random id at the start of the instructions on every model call so no two requests share a prefix",
            "both": "x-portkey-cache-force-refresh: true so Portkey's response cache never replays an old response",
        },
        "verification": verification,
        "summary": summary,
        "runs": runs,
        "calls": calls,
    }, indent=2), encoding="utf-8")

    print("\nsummary:", json.dumps(summary, indent=2))
    print("verification:", verification)
    print("wrote", OUT)
    if leaked or replays:
        sys.exit("FAIL: without_cache read cached tokens or Portkey replayed a response")


if __name__ == "__main__":
    main()
