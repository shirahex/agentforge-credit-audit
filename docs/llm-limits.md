# Language model limits and `LLM_MIN_INTERVAL_SECONDS`

Task I4. The agents call the language model through one client
(`backend/app/llm/client.py`) that sends one call at a time and waits
`LLM_MIN_INTERVAL_SECONDS` between two calls. This page says how many calls
an audit makes, what the free tiers allow, and which interval follows.

## What one audit costs (measured on the six demo files)

Measured by replaying the graph with the client instrumented. One LLM call
per agent step, a second one only when a guard rejects the first answer.

| Demo file | Agent steps = LLM calls without retry | With every answer retried |
|---|---|---|
| approved, borderline | 4 | 8 |
| terms, sensitive | 5 | 10 |
| second_attempt | 7 | 14 |
| no_path (three attempts) | 9 | 18 |

| Agent | Prompt size (system + facts) | Answer cap (`max_tokens`) |
|---|---|---|
| Analyste-Dossier | about 200 tokens | 500 |
| Modèle-Scoring | about 390 tokens | 500 |
| Générateur-Contrefactuels | about 570 tokens | 500 |
| Vérificateur-Équité | about 330 tokens | 500 |
| Arbitre et Rédacteur (French letter) | about 560 tokens | 1,100 |

Prompt sizes are character counts divided by four, which is an estimate; the
exact token counts of a provider are printed by the script below. An audit
therefore sends roughly 2,000 to 3,500 prompt tokens and receives at most
3,100 to 5,600 completion tokens, in 4 to 9 calls.

## What the free tiers allow

Read on 15 November 2026. These figures change often: Groq retired
`llama-3.3-70b-versatile` and `llama-3.1-8b-instant` for free and developer
keys on 16 August 2026 ([Groq deprecations](https://console.groq.com/docs/deprecations)),
so both names now answer HTTP 404. The replacement used here is
`openai/gpt-oss-20b`.

| Provider and model | Per minute | Per day | Source |
|---|---|---|---|
| Groq, `openai/gpt-oss-20b` | 8,000 tokens | 1,000 requests | **Measured on our key** (response headers, below) |
| Gemini, `gemini-3.8-flash` (default in `client.py`) | 5 requests, 250,000 input tokens | 20 requests | [ScriptByAI](https://www.scriptbyai.com/gemini-api-free-tier-limits/), from the table shown in Google AI Studio. Not measured |
| Ollama, local | no quota | no quota | limited by the machine |

Google no longer publishes per-model free quotas in its documentation: they
are shown for each project in Google AI Studio
([Developers Digest](https://www.developersdigest.tech/rate-limits/google), reading the official page on 17 October 2026).
At 20 requests a day, Gemini 3.8 Flash on the free tier would run two to four
audits a day: not usable for this project unless AI Studio shows otherwise.

## Measured on our key: Groq, `openai/gpt-oss-20b`

Measured on 15 November 2026 with `python eval/llm_preflight.py` and
`python eval/measure_llm_limits.py`, free plan, no payment card.

Headers returned by the provider:

| Header | Value |
|---|---|
| `x-ratelimit-limit-requests` | 1,000 (per day) |
| `x-ratelimit-limit-tokens` | 8,000 (per minute) |

`gpt-oss-20b` is a reasoning model: its reasoning is counted in `max_tokens`.
With the answer budgets of the agents (500 tokens), the first call failed
with `json_validate_failed`; with four times the budget it answered. Hence
`LLM_MAX_TOKENS_SCALE=4`, found and written to `backend/.env` by the
preflight script.

One audit of each demo file, `LLM_MIN_INTERVAL_SECONDS=12`:

| Demo file | LLM calls | Prompt tokens | Completion tokens | Steps fallen back to rules | Duration |
|---|---|---|---|---|---|
| approved | 4 | 1,813 | 2,297 | 0 of 4 | 55 s |
| borderline | 4 | 1,855 | 1,953 | 0 of 4 | 56 s |
| sensitive | 6 | 2,984 | 3,567 | 0 of 5 | 84 s |
| terms | 8 | 3,998 | 4,866 | 1 of 7 | 141 s |
| second_attempt | 9 | 5,011 | 5,710 | 0 of 9 | 126 s |
| no_path | 9 | 4,928 | 6,936 | 0 of 9 | 130 s |

Mean: 1,148 tokens per call, of which more than half is completion
(reasoning included). The prompt sizes estimated above (200 to 570 tokens per
call) match the measured prompt tokens.

## Interval to set

    interval = max(60 / requests per minute, 60 x tokens per call / tokens per minute)

| Provider and model | Tokens per call | Tokens per minute | `LLM_MIN_INTERVAL_SECONDS` | Status |
|---|---|---|---|---|
| Groq `openai/gpt-oss-20b` | 1,148 | 8,000 | **10** (8.6 s plus a margin; 12 was used for the runs) | measured |
| Gemini free tier, 5 requests per minute | | | **13** | computed from published figures |
| Ollama | | | **0** | no quota |

Settings retained for Groq, in `backend/.env`:

    LLM_PROVIDER=groq
    LLM_MODEL=openai/gpt-oss-20b
    LLM_MIN_INTERVAL_SECONDS=10
    LLM_MAX_TOKENS_SCALE=4
    STEP_DELAY_SECONDS=0

Consequences for the project:

- An audit takes one to two minutes with this provider, against 0.1 s on
  rules. The live demonstration should use one or two files with the model
  and the others on rules, or a local Ollama model.
- The daily cap of 1,000 requests allows about 150 audits a day. The token
  cap per minute is the binding limit, not the daily one.
- The burst test (`--burst 40`) was not run, to keep the daily quota for the
  evaluation: the per-minute request cap is not measured.

What the client does when a limit is hit: HTTP 429 and 5xx answers are
retried twice with a pause; after that the step falls back to its rules, the
audit continues, and the step is marked `rules` in the trail. An audit never
fails because of the provider.
