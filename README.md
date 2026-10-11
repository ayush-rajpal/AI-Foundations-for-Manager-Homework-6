# AI Foundations for Managers: Homework 6

**Campus Customs vendor desk agent: cost and safety.** A PydanticAI agent on `gpt-6-luna` (via Portkey) reads one
vendor document (HTML quote, PDF quote, or email), extracts vendor / SKU / unit price / lead time / minimum order,
and recommends whether to buy under the Campus Customs Shop Handbook. The homework measures and cuts the token bill
(prompt caching), attacks the agent with prompt-injection documents, and defends it at three levels: code, design
and prompt.

All work is in [`hw6/`](hw6/). The results dashboard is [`hw6/output/hw6_report.html`](hw6/output/hw6_report.html):
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
| `hw6/agent.py` | Main entry point (PydanticAI agent, cache and defense switches, usage + audit logging) |
| `hw6/tools.py` | `read_document` plus the two trap tools `send_email` / `approve_payment` (log only) |
| `hw6/models.py` | Structured output and log-entry models |
| `hw6/defenses.py` | Code-layer document cleaner and design-layer decision engine |
| `hw6/prompts/` | `prompt.md` (defended) and `prompt_undefended.md` (original) |
| `hw6/scripts/` | Test runners for each problem (token count, cache test, attack / defense / red team / exam runs, report builder) |
| `hw6/output/` | Every result file and write-up (`*.json`, `*.md`, `hw6_report.html`, `human_view/` screenshots) |
| `hw6/data/` | Course data: handbook, prices, practice and exam documents, plus `my_attacks/` (Red team) |
| `hw6/AI_prompts.md` | Every prompt used, by problem |

## Run it

```bash
python -m venv C:\venvs\hw6
C:\venvs\hw6\Scripts\python -m pip install -r hw6/requirements.txt
# copy hw6/.env.example to hw6/.env and fill in PORTKEY_API_KEY (.env is git-ignored)
cd hw6
C:\venvs\hw6\Scripts\python agent.py data/exam_docs/e01_quote.html                    # defended agent
C:\venvs\hw6\Scripts\python agent.py --defenses none data/practice_docs/p02_elmcity_quote.html  # original agent
```

`send_email` and `approve_payment` never send or pay anything; they only write to `output/trap_calls.json`, which is
still `[]` after every test.
