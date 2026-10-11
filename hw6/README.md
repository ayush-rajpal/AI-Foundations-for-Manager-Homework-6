# AI Foundations for Managers: Homework 6

**Campus Customs vendor desk agent: cost and safety.** A PydanticAI agent on `gpt-6-luna` (via Portkey) reads one
vendor document (HTML quote, PDF quote, or email), extracts vendor / SKU / unit price / lead time / minimum order,
and recommends whether to buy under the Campus Customs Shop Handbook. The homework measures and cuts the token bill
(prompt caching), attacks the agent with prompt-injection documents, and defends it at three levels: code, design
and prompt.

The results dashboard is [`output/hw6_report.html`](output/hw6_report.html):
download it and open it in a browser. It is one self-contained file that works offline.

## Results at a glance

| | Result |
|---|---|
| Handbook size | 10,062 tokens (measured by the API) |
| Prompt caching | 87.8% cheaper per document ($0.000352 vs $0.002879) |
| Practice attacks that fooled the agent | 4 of 12 before defenses → **0 of 12** after |
| Cost of the defenses | -38% per document (1 model call instead of 2) |
| Exam documents | 10 processed, 5 recommended, 0 trap-tool calls |
| Red team (2 own attack documents) | neither attack succeeded; only the defended agent reported them |
| Projected cost | about **$7.48 / month** at 1,000 documents a day |

## Layout

| Path | What it is |
|---|---|
| `agent.py` | Main entry point (PydanticAI agent, cache and defense switches, usage + audit logging) |
| `tools.py` | `read_document` plus the two trap tools `send_email` / `approve_payment` (log only) |
| `models.py` | Structured output and log-entry models |
| `defenses.py` | Code-layer document cleaner and design-layer decision engine |
| `prompts/` | `prompt.md` (defended) and `prompt_undefended.md` (original) |
| `scripts/` | Test runners for each problem (token count, cache test, attack / defense / red team / exam runs, report builder) |
| `output/` | Every result file and write-up (`*.json`, `*.md`, `hw6_report.html`, `human_view/` screenshots) |
| `data/` | Course data: handbook, prices, practice and exam documents, plus `my_attacks/` (Red team) |
| `AI_prompts.md` | Every prompt used, by problem |

## Run it

Needs Python 3.10+ (built and tested on 3.14) and a Portkey API key with access to `gpt-6-luna`.

**macOS / Linux**

```bash
cd hw6
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your key after PORTKEY_API_KEY=
python agent.py data/exam_docs/e01_quote.html                              # defended agent (default)
python agent.py --defenses none data/practice_docs/p02_elmcity_quote.html  # original, undefended agent
```

**Windows** (keep the venv outside OneDrive: long OneDrive paths break pip installs)

```bash
cd hw6
python -m venv C:\venvs\hw6
C:\venvs\hw6\Scripts\python -m pip install -r requirements.txt
copy .env.example .env        # then paste your key after PORTKEY_API_KEY=
C:\venvs\hw6\Scripts\python agent.py data/exam_docs/e01_quote.html
C:\venvs\hw6\Scripts\python agent.py --defenses none data/practice_docs/p02_elmcity_quote.html
```

Other options: `--no-cache` turns prompt caching off; `--defenses code,prompt` (any mix of `code`, `design`,
`prompt`) runs single defense layers. Paths work from `hw6/` (`data/...`) or from the repo root (`hw6/data/...`).
Every run appends to `output/usage_log.json` and `output/audit_trail.json`. The test runners for each problem are
in `scripts/` (for example `python scripts/exam_run.py`); they call the live API and append to the logs.

`send_email` and `approve_payment` never send or pay anything; they only write to `output/trap_calls.json`, which is
still `[]` after every test.
