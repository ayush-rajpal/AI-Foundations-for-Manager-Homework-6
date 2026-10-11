# Handbook Size and Cost Estimate

The vendor desk agent sends the whole Campus Customs Shop Handbook (`data/shop_handbook.md`) with every
call. This note measures how big it is in tokens and what that costs on `gpt-6-luna`.

## 1. Inputs

**The handbook** (`data/shop_handbook.md`)

| Measure | Value |
|---|---|
| Characters | 28,903 |
| Words | 6,127 |
| Lines | 339 |

**The prices** (`data/prices.json`, gpt-6-luna, OpenAI Standard pricing per 1M tokens, MGT 409 Lecture 11)

| Rate | $ per 1M tokens | $ per token |
|---|---|---|
| Input (uncached) | $0.100 | $0.000000100 |
| Cached input (cache read) | $0.010 | $0.000000010 |
| Cache write | $0.125 | $0.000000125 |
| Output | $0.500 | $0.000000500 |

## 2. Actual token count

### How the token counts were obtained

A token is the unit the model reads and bills by: a chunk of text, often a whole short word, part of a
longer word, or a single symbol like `|` or `$`. Word or character counts can only estimate tokens, so I
counted them directly in two independent ways, both in `scripts/count_handbook_tokens.py`:

```
C:/venvs/hw6/Scripts/python scripts/count_handbook_tokens.py
```

The script reads `data/shop_handbook.md` as UTF-8 text, exactly as the agent will send it. It saves every
raw number to `output/handbook_token_count.json`.

**Method A: offline tokenizer (no API call, free).**
[tiktoken](https://github.com/openai/tiktoken) is OpenAI's own tokenizer library. Its `o200k_base`
encoding is the tokenizer used by the GPT-4o and GPT-5 model families. The script splits the handbook
into tokens and counts them:

```python
enc = tiktoken.get_encoding("o200k_base")
len(enc.encode(HANDBOOK))          # -> 10,058
```

This is a good estimate, but it is not proof of what `gpt-6-luna` actually bills, because the model's
exact tokenizer is not published.

**Method B: ask the API what it billed (live, the ground truth).**
Every response from the API includes a `usage` block with the exact number of input tokens charged. The
script calls `gpt-6-luna` through Portkey (the OpenAI Responses API at `https://api.portkey.ai/v1`, with
`PORTKEY_API_KEY`), sending the handbook as the system `instructions` and a trivial question as input:

```python
client.responses.create(
    model="gpt-6-luna",
    instructions=HANDBOOK,                     # the handbook, as the agent will send it
    input="Reply with the single word OK.",    # tiny question, so output cost is tiny
    max_output_tokens=64,
)
# read response.usage.input_tokens and response.usage.input_tokens_details.cached_tokens
```

`input_tokens` counts **everything** sent, not just the handbook: the handbook, the question, and a few
formatting tokens the API adds to mark where messages start and end. To isolate the handbook, the script
first makes a **baseline call** with the same question but no handbook. It then subtracts:
`handbook = (call with handbook) - (call without handbook)`. Everything except the handbook is identical in
both calls, so the difference is the handbook alone. Finally, the script repeats the handbook call to see
whether any tokens come back as `cached_tokens`.

Results of Method B (live calls to `gpt-6-luna`):

| Call | Handbook sent? | input_tokens | cached_tokens |
|---|---|---|---|
| Baseline: question only ("Reply with the single word OK.") | No | 13 | 0 |
| Handbook as `instructions` + same question, call 1 | Yes | 10,075 | 0 |
| Same as above, call 2 (repeat) | Yes | 10,075 | 0 |

```
handbook tokens = input_tokens with handbook - input_tokens without handbook
                = 10,075 - 13
                = 10,062 tokens
```

The two methods differ by only 4 tokens (10,062 vs 10,058). The extra 4 come from the message wrapper the
API puts around the `instructions` block.

> **Actual handbook token count: N = 10,062 tokens** (as billed by the API). The calculations below use this
> number. So the "about 10,000 tokens" in the assignment brief is correct.

Ratio check: 28,903 chars / 10,062 tokens = **2.87 characters per token**. That is low compared with the
usual ~4 for plain English, because the handbook is mostly markdown tables (`|`, `$`, SKU codes like
`CC-HD-001`), and each of those breaks into many small tokens.

## 3. Cost of the handbook on a single call

Cost = tokens x (price per 1M / 1,000,000)

| Scenario | Calculation | Cost per call |
|---|---|---|
| **Uncached** (full input price) | 10,062 x $0.100 / 1,000,000 | **$0.0010062** (~0.10 cents) |
| **Cached read** (handbook already in cache) | 10,062 x $0.010 / 1,000,000 | **$0.00010062** (~0.01 cents) |
| Cache write (first call that loads the cache) | 10,062 x $0.125 / 1,000,000 | $0.00125775 (~0.13 cents) |

A cached read costs one tenth of an uncached call ($0.010 vs $0.100 per 1M), which is a **90% saving on
every call after the first**. The first call costs 25% more than uncached, because writing the cache
($0.125) is priced above plain input ($0.100).

## 4. Cost of the handbook over 1,000 calls

**Scenario 1: No caching.** All 1,000 calls pay full input price.

```
1,000 x 10,062 = 10,062,000 tokens = 10.062M tokens
10.062M x $0.100 = $1.0062
```

**Scenario 2: Caching (realistic).** Call 1 writes the cache, then calls 2 to 1,000 read from it.

```
Cache write (1 call):   1 x 10,062 x $0.125 / 1M   = $0.00125775
Cache reads (999 calls): 999 x 10,062 x $0.010 / 1M = 10,051,938 tokens x $0.010 / 1M = $0.10051938
Total                                                = $0.10177713  (~$0.1018)
```

**Scenario 3: Caching (ideal ceiling).** All 1,000 calls are cache reads, with no write charge.

```
1,000 x 10,062 x $0.010 / 1M = $0.10062
```

### Summary

| | Per call | 1,000 calls | vs. uncached |
|---|---|---|---|
| Uncached | $0.0010062 | **$1.0062** | |
| Cached (1 write + 999 reads) | $0.000101777 avg | **$0.1018** | saves $0.9044 (**89.9%**) |
| Cached (ideal, all reads) | $0.00010062 | $0.1006 | saves $0.9056 (90.0%) |

```
Savings = $1.0062 - $0.10177713 = $0.90442287
Savings % = $0.90442287 / $1.0062 = 89.9%
```

**When caching starts to pay.** A cache write costs $0.025 per 1M more than an uncached call
($0.125 - $0.100). Each cache read saves $0.090 per 1M ($0.100 - $0.010). The extra write cost is
therefore recovered on the **first reuse**: 0.025 / 0.090 = 0.28 of a call. Caching wins as soon as the
handbook is sent twice.

## 5. What this means

- **The handbook dominates the input bill.** The baseline question was 13 tokens. A vendor document will
  add a few hundred to a few thousand more. The handbook is 10,062 tokens of fixed overhead on every call,
  most likely the majority of the input on every call.
- **Small per call, but it scales.** About $1 per 1,000 calls uncached becomes about $1,006 per million
  calls. Since the handbook never changes between calls, almost all of that is wasted repetition.
- **Caching cuts the bill by about 90%.** To get that discount, the handbook has to sit at the **start** of
  the prompt, byte-for-byte identical on every call, with the vendor document placed after it. Caching
  works on prompt prefixes, so anything that changes before the handbook breaks the cache.
- **Caching is not automatic.** Our two back-to-back handbook calls both reported `cached_tokens = 0`. The
  cached rate is a ceiling we have to earn, not a given; it still has to be switched on and checked in
  practice. Other ways to cut the bill are sending only the handbook sections the agent needs (§4 rules,
  §5–6 vendor lists, §9 catalogue), or looking up a single SKU instead of sending the whole catalogue table.
- **Output is not included above.** These numbers cover only the handbook's input cost. Output tokens cost
  $0.500 per 1M (5x input), so a 200-token answer adds 200 x $0.5 / 1M = $0.0001 per call.
