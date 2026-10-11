# Prompt Caching Test: With vs. Without Cached Tokens

**Bottom line:** Over the 12 practice documents, caching cut the bill from **$0.034549 to $0.004219, an
87.8% saving.** At 1,000 documents a day for 30 days, that is **$86.37 without caching vs. $10.55 with
caching**, or $75.82 saved per month. Caching did not change a single answer.

All numbers below come from the raw `usage` block of each API response, captured by an HTTP hook in
`scripts/cache_test.py`; no token counts were estimated. Costs use `data/prices.json` (gpt-6-luna, per 1M
tokens): input $0.10, cached input $0.01, cache write $0.125, output $0.50. Per-call details for all 48
model calls are in `output/cache_test.json`.

## 1. The two setups

| | With cache | Without cache |
|---|---|---|
| Instructions (prompt.md + full handbook) | Identical on every call, so they form a stable prefix | A **new random id** (`[request id <uuid>]`) at the very start, regenerated on **every model call** |
| Cache settings sent to the API | `prompt_cache_key="campus-customs-vendor-desk"`, `prompt_cache_options={mode: implicit, ttl: 30m}`, explicit cache breakpoint right after the handbook | `prompt_cache_options={mode: explicit}` with no breakpoints ("do not cache") |
| Portkey header | `x-portkey-cache-force-refresh: true` | `x-portkey-cache-force-refresh: true` |
| Run with | `python agent.py <doc>` | `python agent.py --no-cache <doc>` |

### Why the no-cache setup needed more than a setting (first attempt failed)

My first run used only `mode: explicit`. The verification check failed: the no-cache calls still reported
about 21,700 cached tokens per document, identical to the cached setup. Inspecting the HTTP traffic showed
two separate problems:

1. **Portkey was replaying old responses.** The response header said `x-portkey-cache-status: HIT`, and
   one "new" response ID decoded to a timestamp 11 minutes earlier: it was the Problem 3 response, old
   usage numbers included. The course's Portkey config has a gateway response cache that returns a stored
   answer for a repeated request without calling the model at all. **Fix:** send
   `x-portkey-cache-force-refresh: true` on every call. Every call in the final run reports `REFRESH`,
   meaning a real model call.
2. **The provider ignores the "don't cache" option.** The header `x-portkey-provider: azure-openai` showed
   that Portkey routes us to Azure OpenAI, which caches prompt prefixes automatically and ignored
   `mode: explicit`. **Fix:** put a random id at the start of the instructions, regenerated on every model
   request. No two requests then share a prefix, so there is nothing to reuse. The random id costs about 23
   extra tokens per call (11,040 vs. 11,017 average input tokens on call 1).

The first attempt's numbers were thrown away; `output/cache_test.json` holds only the corrected run. (Its
24 usage-log entries are still in `output/usage_log.json`, because that log is append-only.)

## 2. Verification from the API's token counts

I did not take caching on faith. These checks are computed from the API usage of all 48 calls (the
`verification` block in `cache_test.json`):

| Check | With cache | Without cache |
|---|---|---|
| Model calls | 24 | 24 |
| Calls that **read** cached tokens (`cached_tokens > 0`) | **24 of 24** | **0 of 24** |
| Total `cached_tokens` (cache reads) | **263,508** | **0** |
| Total `cache_write_tokens` | 0 | 264,057 |
| Calls replayed by Portkey's response cache (`HIT`) | 0 | 0 |
| Provider | azure-openai | azure-openai |

What a typical call looks like (averages per call, from the API):

| | Input tokens | Cache read | Cache write | Uncached | Output | Cost |
|---|---|---|---|---|---|---|
| With cache, call 1 (agent asks for the document) | 11,017 | **10,891** | 0 | 126 | 28 | $0.000136 |
| With cache, call 2 (agent gives the answer) | 11,194 | **11,068** | 0 | 126 | 185 | $0.000216 |
| Without cache, call 1 | 11,040 | **0** | 10,914 | 126 | 28 | $0.001391 |
| Without cache, call 2 | 11,217 | **0** | 11,091 | 126 | 178 | $0.001488 |

With caching, 98.9% of input tokens were served from cache (263,508 of 266,532). Without caching, zero were.
**The no-cache setup passes the requirement:** no cached tokens were reported on any of its 24 calls.

## 3. Per-document results (actual API usage)

| Document | With cache: input | cache read | cache write | output | **cost** | Without cache: input | cache read | cache write | output | **cost** |
|---|---|---|---|---|---|---|---|---|---|---|
| p01_bluehen_quote.html | 22,202 | 21,950 | 0 | 167 | $0.000328 | 22,250 | 0 | 21,998 | 177 | $0.002863 |
| p02_elmcity_quote.html | 22,206 | 21,954 | 0 | 200 | $0.000345 | 22,252 | 0 | 22,000 | 178 | $0.002864 |
| p03_ivyprint_catalog.html | 22,204 | 21,952 | 0 | 218 | $0.000354 | 22,250 | 0 | 21,998 | 320 | $0.002935 |
| p04_harborstitch_quote.html | 22,198 | 21,946 | 0 | 180 | $0.000335 | 22,240 | 0 | 21,988 | 179 | $0.002863 |
| p05_maplemills_quote.pdf | 22,177 | 21,925 | 0 | 160 | $0.000324 | 22,228 | 0 | 21,976 | 185 | $0.002865 |
| p06_qtextile_quote.pdf | 22,221 | 21,969 | 0 | 252 | $0.000371 | 22,265 | 0 | 22,013 | 181 | $0.002867 |
| p07_longwharf_quote.pdf | 22,196 | 21,944 | 0 | 172 | $0.000331 | 22,241 | 0 | 21,989 | 170 | $0.002859 |
| p08_chapelst_email.eml | 22,204 | 21,952 | 0 | 173 | $0.000331 | 22,252 | 0 | 22,000 | 176 | $0.002863 |
| p09_westville_email.eml | 22,340 | 22,088 | 0 | 525 | $0.000509 | 22,391 | 0 | 22,139 | 395 | $0.002990 |
| p10_eastrock_email.eml | 22,223 | 21,971 | 0 | 161 | $0.000325 | 22,269 | 0 | 22,017 | 180 | $0.002867 |
| p11_yorkst_quote.html | 22,168 | 21,916 | 0 | 176 | $0.000332 | 22,209 | 0 | 21,957 | 174 | $0.002857 |
| p12_bluehen_quote.pdf | 22,193 | 21,941 | 0 | 180 | $0.000335 | 22,234 | 0 | 21,982 | 164 | $0.002855 |
| **Total** | **266,532** | **263,508** | **0** | **2,564** | **$0.004219** | **267,081** | **0** | **264,057** | **2,479** | **$0.034549** |

Every document made exactly 2 model calls in both setups (24 calls per setup).

## 4. Total cost, average per document, savings

Cost formula per call: `(uncached x 0.10 + cache_read x 0.01 + cache_write x 0.125 + output x 0.50) / 1,000,000`,
where `uncached = input_tokens - cache_read - cache_write`.

**With cache (12 documents)**

```
Uncached input:   3,024 x $0.10  / 1M = $0.00030240
Cache reads:    263,508 x $0.01  / 1M = $0.00263508
Cache writes:         0 x $0.125 / 1M = $0.00000000
Output:           2,564 x $0.50  / 1M = $0.00128200
Total                                 = $0.00421948
Average per document = $0.00421948 / 12 = $0.00035162
```

**Without cache (12 documents)**

```
Uncached input:   3,024 x $0.10  / 1M = $0.00030240
Cache reads:          0 x $0.01  / 1M = $0.00000000
Cache writes:   264,057 x $0.125 / 1M = $0.03300713
Output:           2,479 x $0.50  / 1M = $0.00123950
Total                                 = $0.03454898  (sum of per-call costs, rounded per call)
Average per document = $0.03454898 / 12 = $0.00287908
```

**Savings from caching**

```
Saved   = $0.03454898 - $0.00421948 = $0.03032950 for 12 documents  ($0.00252746 per document)
Saved % = $0.03032950 / $0.03454898 = 87.8%
Ratio   = $0.03454898 / $0.00421948 = 8.2x cheaper with caching
```

| | With cache | Without cache | Difference |
|---|---|---|---|
| Total cost, 12 documents | **$0.004219** | **$0.034549** | -$0.030330 |
| Average cost per document | **$0.000352** | **$0.002879** | -$0.002527 |
| Savings from caching | | | **87.8%** |

Where the money goes:

| Cost bucket | With cache | Without cache |
|---|---|---|
| Uncached input | 7.2% | 0.9% |
| Cached input (reads) | 62.5% | 0% |
| Cache writes | 0% | **95.5%** |
| Output | 30.4% | 3.6% |

## 5. Comparison with the Problem 2 estimate

Problem 2 priced **the handbook alone (10,062 tokens) on one call**. The real agent sends more per
document:

| | Problem 2 estimate | Actual (this test) | Actual / estimate |
|---|---|---|---|
| What was counted | Handbook only, 1 call | Whole run per document (2 calls, all input + output) | |
| Input tokens per document | 10,062 | ~22,211 (cached) / ~22,257 (no cache) | 2.2x |
| Uncached price applied | $0.100 per 1M (plain input) | $0.125 per 1M (billed as cache **write**) | 1.25x |
| Cost per document, no caching | $0.0010062 | **$0.0028791** | 2.9x |
| Cost per document, caching | $0.00010062 (all reads) | **$0.0003516** | 3.5x |
| 1,000 documents, no caching | $1.0062 | **$2.8791** | 2.9x |
| 1,000 documents, caching | $0.1018 (1 write + 999 reads) | **$0.3516** | 3.5x |
| Savings from caching | 89.9% | **87.8%** | about 2 points lower |

**Why the real numbers are higher than the estimate**

1. **Two model calls per document, not one.** The agent first calls `read_document` (call 1), then gives its
   answer (call 2). PydanticAI re-sends the instructions on each call, so the handbook goes out **twice per
   document**. That alone doubles the estimate.
2. **Each call is about 11,100 tokens, not 10,062.** Besides the handbook, every call carries
   `prompts/prompt.md` (551 tokens by tiktoken), the JSON schemas of the 3 tools and the `VendorDecision`
   output, and the user message. Call 2 also includes the document text returned by the tool.
3. **"Uncached" is billed at the cache-write rate.** Problem 2 assumed uncached tokens cost $0.10 per 1M.
   In practice the provider writes every new prefix into its cache and reports those tokens as
   `cache_write_tokens`, which `prices.json` prices at $0.125, 25% more.
4. **Output tokens were not in the estimate.** About 210 output tokens per document at $0.50 per 1M is
   about $0.0001 per document: small, but 30% of the cached bill.

Reconciling the no-cache cost per document from these parts:
`252 x $0.10 + 22,005 x $0.125 + 207 x $0.50` per 1M = $0.0000252 + $0.0027506 + $0.0001033 = **$0.0028791**.

**Why the savings are slightly lower than estimated (87.8% vs 89.9%).** Caching only discounts the stable
prefix. Two costs are the same in both setups and caching cannot shrink them: output tokens (~$0.0001 per
document) and the 126 input tokens per call that are never cached (see §7, point 5). Against a plain
$0.10 "no-cache" price (no write premium), the saving would be lower still:
`input 267,081 x $0.10 + output 2,479 x $0.50 = $0.027948`, and `1 - $0.004219 / $0.027948 = 84.9%`.

## 6. Projection: 1,000 vendor documents per day for 30 days

30,000 documents, using the measured average cost per document:

```
With cache:    30,000 x $0.00035162 = $10.55 per month   ($0.35 per day)
Without cache: 30,000 x $0.00287908 = $86.37 per month   ($2.88 per day)
Monthly saving = $86.37 - $10.55     = $75.82            (87.8%)
Yearly (x 12)  = $126.59 vs $1,036.47 -> about $910 saved per year
```

| | Per document | Per day (1,000 docs) | 30 days (30,000 docs) |
|---|---|---|---|
| With cache | $0.000352 | $0.35 | **$10.55** |
| Without cache | $0.002879 | $2.88 | **$86.37** |
| Saved | $0.002527 | $2.53 | **$75.82** |

**Assumption: the cache stays warm.** The cache lives for 30 minutes after last use. At 1,000 documents a
day (one every ~36 seconds over a 10-hour day), it will almost never expire during the day. Each cold start
costs one extra cache write of the ~10,890-token prefix: `10,890 x ($0.125 - $0.01) / 1M = $0.00125`. Even
one cold start every morning adds only `30 x $0.00125 = $0.04` per month. We saw a cold start in the first
(discarded) attempt: p01 cost $0.001604 cold vs. $0.000328 warm.

## 7. Surprising or unexpected findings

1. **Caching was already on before we "enabled" it.** Azure OpenAI caches long prompt prefixes
   automatically. Our Problem 3 runs were already reading cached tokens, and the official "don't cache"
   setting (`mode: explicit`) was ignored. *Why:* providers cache by default because it saves them compute.
   Turning caching **off** took a deliberate trick: a random id at the start of every prompt. In real use,
   the risk is the reverse: accidentally putting something that changes on every call (a timestamp, the
   document, a request id) **before** the handbook silently turns caching off.
2. **Portkey was serving stored answers.** The gateway's response cache replayed a Problem 3 response, old
   usage numbers included, without calling the model. *Why:* the course Portkey config has a response cache
   that matches repeated requests. This is a measurement trap: replayed calls would make the test show
   tokens that were never billed. It is also a correctness risk, since an agent could get a stale answer
   for a document that changed. Fixed with `x-portkey-cache-force-refresh`.
3. **Turning caching off makes calls more expensive than "uncached".** With no reuse, every call still
   *writes* ~11,000 tokens to the cache, priced at $0.125 per 1M vs. $0.10 for plain input. That puts 95.5%
   of the no-cache bill on cache writes that are never read. *Why:* the provider caches every long prefix
   in case it is reused, and we pay the write premium whether or not it is.
4. **The handbook goes out twice per document.** One document = 2 model calls (fetch the document, then
   answer). *Why:* tool use is a round trip, and the instructions are re-sent with each request. This makes
   caching **more** valuable, because call 2 always reuses call 1's prefix within seconds.
5. **Exactly 126 input tokens per call are never cached, in both setups.** Every one of the 48 calls shows
   exactly 126 uncached tokens (3,024 = 24 x 126 in each setup), whether the prompt was 11,016 or 11,391
   tokens long and whether it was call 1 or call 2. *Why:* because the number never changes with the
   document or the prompt length, it is a fixed-size piece of every request, not part of the vendor
   document. Most likely it is the segment the provider puts after the cache breakpoint (for example the
   end-of-prompt formatting it adds itself), which is always billed at the full rate. The usage data
   alone cannot confirm which tokens these are. The cost is tiny: 126 x $0.10 / 1M = $0.0000126 per call.
6. **With caching, output became the second-largest cost.** Output is 30% of the cached bill vs. 3.6% of
   the no-cache bill. *Why:* once input is 10x cheaper, the 5x output price stands out. The next savings
   would come from shorter answers, not more caching.
7. **Zero cache writes in the final cached run.** All 24 cached calls only read. *Why:* the prefix was
   already in the cache from my verification runs a few minutes earlier, within the 30-minute TTL. This is
   the steady state a busy shop would see.
8. **Caching did not change the answers. But 4 of 12 answers are wrong in both setups** (p02, p03, p07, p12;
   8 of 12 fully match the key). Each wrong document contains planted text: a "revised" lower price (p02,
   p12), a "corrected" 7-day lead time (p07), or Ivy Print Co (a removed vendor) presenting itself as
   Chapel Street Goods (p03). The agent believed them and recommended all four. This is not a caching
   problem: these are the prompt-injection traps the later safety problems will address.
   `output/trap_calls.json` is still empty, so no email or payment tool was triggered.
