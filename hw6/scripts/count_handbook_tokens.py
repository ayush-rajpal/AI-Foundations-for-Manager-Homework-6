"""Count the tokens in data/shop_handbook.md two ways and save the numbers.

1. Offline: tiktoken o200k_base (the GPT-4o / GPT-5 family tokenizer).
2. Live: send the handbook to gpt-6-luna through Portkey and read the token
   counts the API bills us for. A tiny baseline call (no handbook) is
   subtracted so the message wrapper is not counted as handbook. A repeat call
   shows how many handbook tokens come back as cached.

Run:  C:/venvs/hw6/Scripts/python scripts/count_handbook_tokens.py
Writes output/handbook_token_count.json
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

HW_DIR = Path(__file__).resolve().parents[1]
for folder in [HW_DIR, *HW_DIR.parents]:
    if (folder / ".env").exists():
        load_dotenv(folder / ".env", override=False)

MODEL = "gpt-6-luna"
HANDBOOK = (HW_DIR / "data" / "shop_handbook.md").read_text(encoding="utf-8")
QUESTION = "Reply with the single word OK."

client = OpenAI(
    api_key=os.environ["PORTKEY_API_KEY"],
    base_url=os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1"),
    default_headers={"x-portkey-provider": "openai"},
)


def call(instructions: str | None) -> dict:
    kwargs = {"model": MODEL, "input": QUESTION, "max_output_tokens": 64}
    if instructions:
        kwargs["instructions"] = instructions
    r = client.responses.create(**kwargs)
    u = r.usage
    cached = getattr(u.input_tokens_details, "cached_tokens", 0) or 0
    return {
        "input_tokens": u.input_tokens,
        "cached_tokens": cached,
        "output_tokens": u.output_tokens,
        "status": r.status,
    }


def main() -> None:
    enc = tiktoken.get_encoding("o200k_base")
    offline = {
        "characters": len(HANDBOOK),
        "words": len(HANDBOOK.split()),
        "lines": HANDBOOK.count("\n") + 1,
        "tiktoken_o200k_base": len(enc.encode(HANDBOOK)),
    }
    print("offline:", offline)

    baseline = call(None)
    print("baseline (no handbook):", baseline)
    first = call(HANDBOOK)
    print("with handbook, call 1:", first)
    time.sleep(2)
    second = call(HANDBOOK)
    print("with handbook, call 2:", second)

    result = {
        "model": MODEL,
        "offline": offline,
        "api": {
            "baseline_no_handbook": baseline,
            "handbook_call_1": first,
            "handbook_call_2": second,
            "handbook_tokens_by_api": first["input_tokens"] - baseline["input_tokens"],
        },
    }
    out = HW_DIR / "output" / "handbook_token_count.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("handbook tokens (API, minus baseline):", result["api"]["handbook_tokens_by_api"])
    print("wrote", out)


if __name__ == "__main__":
    main()
