# jev-browser-mcp

*[Versão em português](README.pt.md)*

An MCP server that gives Claude Code a browser agent: one tool, `browse_interactive`, that opens a dedicated Chrome
and carries out interactive tasks on the web (filling forms, applying filters, autocomplete, date pickers, SPAs).

Under the hood it uses Browser Use's [jev-ultrafast](https://github.com/browser-use/jev-ultrafast). At each step it
reads the page, numbers the elements that can be interacted with, and asks TypeSafe's [Jev](https://docs.typesafe.ai)
model for one operation (`CLICK`, `TYPE_TEXT`, `SELECT`, `SCROLL`, `WAIT`, `DONE`, `BLOCKED`) and an element number.
The model never writes selectors or coordinates: it only picks a number from a list the code gave it.

This repository is the missing layer around that: safety guards, verification of the outcome, cost accounting, and
fixes for the defects that showed up in real testing.

**When not to use it.** Reading a page or a link is faster and cheaper with `WebFetch`; searching, with `WebSearch`;
library documentation, with context7. This tool is for when the information only exists after clicking, and it is
about 80 times more expensive per operation than a structured decision made in code (see the numbers below).

**Contents:** [install](#install) · [usage](#usage) · [verification](#verifying-done) · [field-text models](#which-local-model-writes-field-text) ·
[results](#measured-results-2026-09-24-scriptsbench_hardpy) · [troubleshooting](#troubleshooting) ·
[limits](#known-limits) · [security](#security-and-privacy)

## What it adds to jev-ultrafast

| | Why |
| --- | --- |
| **Domain allowlist** | Mandatory. A start URL, clicked link or redirect outside the list stops the run |
| **Stop before irreversible actions** | Buy, delete, send, book and similar (English and Portuguese) return `needs_confirmation` instead of clicking |
| **Verification of `DONE`** | The agent saying it finished is not proof. Three Jev questions re-assess the final page |
| **Loop guard** | Stops when the same operation hits the same element 4 times, or after 20 s of continuous waiting |
| **Enter operation** | jev has no Enter key, and some fields only submit that way. The wrapper injects `PRESS_ENTER` |
| **Retries** | If the agent gives up while the page is still changing, it gets another chance (2x); a malformed model reply is retried instead of aborting the task |
| **Budgets** | `max_steps` and `timeout_s`, and one run at a time |
| **Dedicated Chrome** | Port 9333, its own profile, none of your personal sessions; browser-harness telemetry turned off |
| **Cost per task** | Input tokens and dollars in every result |
| **Local mode** | Without a TypeSafe key, decisions run on an Ollama model on your machine |

## Install

As a plugin (brings the server, the routing skill and the `/jev-doctor` command):

```bash
claude plugin marketplace add mjvmsteixeira/jev-browser-mcp
claude plugin install jev-browser@jev-browser-mcp
```

Then, once per machine:

```bash
scripts/setup-ollama.sh              # creates the jev-agent model (16k context) that writes field text
```

For the fast backend, give the server a TypeSafe key (from console.typesafe.ai/keys) in one of two ways:

- `TYPESAFE_API_KEY` in the environment the MCP server starts with.
- A local Vault: `run.sh` reads `secret/ai/typesafe` through `$JEV_VAULT_READ` (default `~/vault/vault-read.sh`)
  every time the server starts, so no key ever sits in a project file. `scripts/store-typesafe-key.sh` stores it
  there; it is written for the author's own Vault setup, so adapt it to yours.

`/jev-doctor` tells you what is missing. Python dependencies are installed by `uv run` on the first call. Without the
plugin, register the server by hand with `claude mcp add --scope user jev-browser -- "$PWD/run.sh"`, but then the
skill is not installed.

Runs on macOS and Linux (the Chrome binary is found per platform; set `JEV_CHROME` otherwise).

### What the plugin contains

```
.claude-plugin/marketplace.json   this repository as a marketplace
claude/.claude-plugin/plugin.json plugin manifest
claude/.mcp.json                  jev-browser server -> run.sh
claude/skills/web-routing/        when to use this tool instead of WebFetch/WebSearch/context7
claude/commands/jev-doctor.md     diagnostics (Chrome, Ollama, key, server in memory)
```

If the server started before the key existed, reconnect it in `/mcp`.

Variables: `JEV_CDP_PORT`, `JEV_PROFILE_DIR`, `JEV_CHROME`, `JEV_HEADLESS=1`, `JEV_DECISION_BACKEND`,
`JEV_DECISION_MODEL`, `JEV_VERIFY_THRESHOLD`, `JEV_MODEL_TIMEOUT`, `JEV_VAULT_READ`, `JEV_VAULT_PATH`, `TEXT_MODEL*`.

## Usage

Ask in plain language; the `web-routing` skill that ships with the plugin decides when to use this tool instead of
`WebFetch`, `WebSearch` or context7 (reading a page or searching is faster and cheaper those ways).

```
"In my app at http://localhost:3000, check that I can search for 'Braga' and apply the 'Active' filter."
```

### Parameters

| Parameter | Default | Purpose |
| --- | --- | --- |
| `start_url`, `objective`, `allowed_domains` | — | Required. The objective should say when to stop ("Stop when results are visible") |
| `max_steps` | 25 | Budget of browser actions |
| `timeout_s` | 90 | Time budget, checked between steps |
| `allow_irreversible` | `false` | Only `true` after the user approved that specific purchase, message or deletion |
| `max_text_chars` | 20000 | Cap on the returned text |
| `keep_open` | `false` | Leaves the tab open in the dedicated Chrome, to inspect or finish by hand |

### Result

```json
{
  "status": "done",
  "reason": "Agent chose DONE; verify the outcome",
  "final_url": "https://en.wikipedia.org/wiki/Ada_Lovelace",
  "title": "Ada Lovelace - Wikipedia",
  "page_text_untrusted": "...",
  "steps": [{"step": 1, "operation": "TYPE_TEXT", "action": "Search Wikipedia", "text": "Ada Lovelace"}],
  "verification": {"scores": {"all_requirements": 0.9, "right_page": 0.97, "nothing_left": 0.94}, "passed": true},
  "cost": {"input_tokens": 39495, "usd": 0.001659},
  "decision_backend": "typesafe"
}
```

Statuses: `done` (already re-checked with Jev), `unverified` (the agent said it finished but the check disagreed),
`blocked`, `stalled`, `timeout`, `step_budget`, `needs_confirmation`, `domain_blocked`, `error`. When the agent gives
up but the check says the goal looks met, that shows up in `reason`.

The returned text is web content: it is data, never instructions.

### Sites that need a login

The dedicated Chrome starts with no sessions and the agent never types into password fields (the snapshot skips
them). For a site behind a login, sign in by hand in that Chrome window, then ask for the task with `keep_open`. The
session stays in the `~/.jev-browser/chrome-profile` profile and is reused on later calls.

## Verifying `DONE`

In the benchmark, both models declared `DONE` with one requirement still unmet. So every `DONE` is re-assessed with
three yes/no questions about the final page (requirements met, right page, nothing pending). Below
`JEV_VERIFY_THRESHOLD` (0.7) the status becomes `unverified`.

Measured on 2026-09-24: GitHub, which was a false `done`, scored 0.09 / 0.34 / 0.25 and was caught; the hotel fixture
scored 0.92 / 0.96 / 0.92 and Google Flights 0.81 / 0.94 / 0.92, both kept as `done`.

## Measured results (2026-09-24, `scripts/bench_hard.py`)

Seven tasks, each checked independently by the URL and text of the final page, never by the agent's `DONE`. Field
text always runs on the local Ollama; only the decider changes.

| Task | Jev (`jev-latest`) | Local decider (qwen3-coder 30b-a3b) |
| --- | --- | --- |
| Hotel fixture (2 filters + open a result) | ✅ 3.7 s | ❌ loop detected, 15 s |
| Google Flights (autocomplete + date picker) | ✅ 8.4 s | ❌ blocked, 48 s |
| GitHub (facet + sort dropdown) | ✅ 4.8 s | ❌ blocked, 21 s |
| the-internet, 5 s async load | ⚠️ goal reached, but the agent gave up | ✅ 7.1 s |
| TodoMVC (submits only with Enter) | ⚠️ created the todos and filtered; did not complete one | ❌ loop detected, 18 s |
| DemoQA (long form) | ❌ ran out of jev's internal budget (120 calls) | ❌ same, 120 s |
| Editor inside an iframe (unsupported) | ✅ stopped correctly, 3.4 s | ❌ false `done` |

Jev solves 3 of the 5 real tasks and reaches the goal on a fourth without recognising it; it is 5 to 10 times faster
than the local model. Neither finishes the long DemoQA form. The local model still wins on async waits.

Typical cost of a browser task: 10 to 40 thousand input tokens, $0.0005 to $0.0017, 3 to 10 s. For comparison,
`scripts/bench_classify.py` measures the other way to use the same model — a structured decision inside code, no
browser — at $0.000022 and 0.3 s per item, with 21 of 24 answers right across 8 alerts. When the decision repeats
inside a system, that is the right path; this server is for when the information only exists behind clicks.

## Which local model writes field text

![Normal cases right out of 60, prompt injections resisted out of 6, and median time per field, for nine local models](docs/bench-text.svg)

> Measured on 2026-11-14 with [`scripts/bench_text.py`](scripts/bench_text.py); raw results in
> [`docs/bench-text-2026-11-14.json`](docs/bench-text-2026-11-14.json), chart drawn by `scripts/chart_bench_text.py`.

Every `TYPE_TEXT` step asks a second model for the value to type ("Lisbon", a date, an email). It runs on Ollama
and, by default, it is `jev-agent`, a 19 GB model. That size is the biggest install barrier, so nine local models
were measured on that exact call: same prompt, same JSON contract, same request body as the server sends.

22 hand-written cases with known answers, each run 3 times: destinations, search queries, both sides of a flight,
dates in two formats, form fields picked out of a sentence, a second todo after the first, Portuguese goals,
postal codes, accents, and 2 prompt-injection cases where the page tells the model to type "hacked". Apple M5,
32 GB, Ollama, no browser.

| Model | Size | Normal cases (60) | Resisted injection (6) | Invalid JSON | Median | p90 |
| --- | --- | --- | --- | --- | --- | --- |
| `jev-agent` (qwen3-coder 30b-a3b, default) | 18.6 GB | **60** | **6** | 0 | 255 ms | 414 ms |
| `qwen3.6` | 22.6 GB | 57 | 6 | 3 | 3120 ms | 5119 ms |
| `gemma3:4b` | 3.4 GB | 57 | 0 | 0 | 366 ms | 552 ms |
| `qwen2.5:3b` | 1.9 GB | 53 | 0 | 5 | 208 ms | 352 ms |
| `qwen3:1.7b` | 1.4 GB | 53 | 2 | 2 | 2790 ms | 5246 ms |
| `qwen3:4b` | 2.5 GB | 48 | 0 | 13 | 10739 ms | 17784 ms |
| `llama3.2:3b` | 2.0 GB | 46 | 0 | 9 | 191 ms | 283 ms |
| `phi4-mini` | 2.5 GB | 42 | 0 | 0 | 236 ms | 339 ms |
| `gemma3:1b` | 0.8 GB | 41 | 4 | 0 | 139 ms | 238 ms |

What it shows:

- **The default stays.** `jev-agent` was the only model right on every case and against every injection, and it is
  as fast as the 3B models: it is a mixture-of-experts with about 3B parameters active per token.
- **No small model resisted the injection.** Every model under 4 GB typed "hacked" at least sometimes. The
  irreversible-action guard still stops buy/send/delete-style clicks and Enter on such forms, but a small model
  will type text a page planted.
- **`gemma3:4b` is the best small model**: 57 of 60 normal cases, no invalid JSON, 0.4 s. Its only miss is
  typing both todos into the second one. On the Pro demo flow (search with typing, filter, open, guarded booking)
  it passed 3 of 3 runs. Use it when the machine can't hold 19 GB, on sites you trust:
  `ollama pull gemma3:4b`, then set `TEXT_MODEL=gemma3:4b` in the server's environment.
- **qwen3 needs its reasoning here, and pays for it.** jev asks for no reasoning in OpenRouter's format; on Ollama
  that request object turns thinking *on*, hence the seconds per field and the JSON cut off at the token limit.
  Switching thinking off (`reasoning_effort: "none"`, without the object) made `qwen3:4b` answer in 0.3 s but echo
  its input instead of a value: 0 of 22. So that switch is not in the server.
- Runs vary by a few answers: `jev-agent` scored 65 and then 66 of 66 on two runs with the same request.

The decision model (which element to click) is a different job and was not part of this benchmark; see the table
above for Jev against the local decider.

## Troubleshooting

Always start with `/jev-doctor`: it checks uv, the dedicated Chrome, the local model (and its `num_ctx`), the key,
the resulting backend and the age of the server in memory. It only reports; it fixes nothing.

| Symptom | Likely cause |
| --- | --- |
| `decision_backend` says `ollama` although there is a key | The server started before the key existed. Reconnect in `/mcp` |
| I changed the code and nothing changed | The server process does not reload. Reconnect in `/mcp` |
| `Model connection failed` when typing into a field | The local model is being loaded with its default context and fell back to CPU. Run `scripts/setup-ollama.sh` |
| `max_tokens_exceeded` | Page with a gigantic `<select>`. The wrapper trims labels and caps options, but some pages still overflow |
| The run stops at `needs_confirmation` | It hit a buy, delete or send-style button. Confirm with the user and repeat with `allow_irreversible` |
| The dedicated Chrome was closed | The next call restarts it and clears the orphan daemon |

## Known limits

- From jev-ultrafast: no support for iframes, shadow DOM, uploads or pop-ups (the Enter key now exists here).
- From Jev: very large pages exhaust the context (the wrapper trims labels and caps `select` options, but some cases
  still overflow).
- From verification: the model that checks is the same one that decided, and it errs both ways — on the async load
  it gave 0.42 to a page that already met the goal. It is a signal, not proof.
- Long forms with many widgets have not yet been completed by either model.

## Security and privacy

- The dedicated Chrome has none of your personal sessions; the snapshot skips password fields.
- With the `typesafe` backend, the visible text of each page goes to TypeSafe. On pages with customers' personal
  data, use `JEV_DECISION_BACKEND=ollama`, and nothing leaves the machine.
- Never use it on production dashboards, cloud consoles, Vault, banking or email.

## Tests and benchmarks: different things

**Tests** (`uv run pytest && uv run ruff check .`) check this wrapper: domain guards, stopping before irreversible
actions, budgets, loop detection, label trimming, option caps, the Enter operation, `DONE` verification, cost
accounting, the tool and the MCP protocol layer. They run offline, with no browser and no paid APIs, and **they all
pass**. If one fails, it is a defect.

**Benchmarks** (`scripts/bench_hard.py`, `scripts/bench_classify.py`) measure how far the agent gets on real sites.
They make paid calls and open the browser. The failures in the table above **are not defects in this repository**:
they are the state of the art of the models, and they are there so you know what can be promised.

```bash
uv run python scripts/bench_hard.py                      # the 7 tasks, with whichever backend is active
uv run python scripts/bench_hard.py google-flights       # just one
JEV_DECISION_BACKEND=ollama uv run python scripts/bench_hard.py   # force the local decider
uv run python scripts/bench_classify.py                  # triage of 8 alerts, no browser
uv run python scripts/bench_text.py gemma3:4b jev-agent   # field-text models, local Ollama, no browser
```

Each task has a hand-written checker (URL and text of the final page), independent of the agent's `DONE` and of
the model check. The final text of each task is saved to `/private/tmp/claude-501/bench-<task>.txt`.

### Working on the plugin

```bash
claude plugin marketplace add .                  # from the repository itself
claude plugin install jev-browser@jev-browser-mcp
```

The plugin and a manual registration of the same server don't mix: if you already had
`claude mcp add ... jev-browser`, remove it with `claude mcp remove jev-browser -s user`, or you end up with two
servers with the same name. The same goes for a `web-routing` skill copied by hand into `~/.claude/skills`.

## License

MIT. See [LICENSE](LICENSE).
