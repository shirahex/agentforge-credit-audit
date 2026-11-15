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

Read on 15 November 2026. These figures change often and the public tables
disagree with each other, so the last column says where each one comes from.
They are not measurements on our key.

| Provider and model | Per minute | Per day | Source |
|---|---|---|---|
| Groq, `llama-3.3-70b-versatile` | 30 requests, 12,000 tokens | 1,000 requests, 100,000 tokens | [Grizzly Peak Software](https://grizzlypeaksoftware.com/articles/p/groq-api-free-tier-limits-in-2026-what-you-actually-get-uwysd6mb), quoting Groq's documentation. Other tables give 6,000 tokens per minute or 14,400 requests per day |
| Groq, `llama-3.1-8b-instant` | 30 requests, 6,000 tokens | 14,400 requests, 500,000 tokens | same |
| Gemini, `gemini-3.8-flash` (default in `client.py`) | 5 requests, 250,000 input tokens | 20 requests | [ScriptByAI](https://www.scriptbyai.com/gemini-api-free-tier-limits/), from the table shown in Google AI Studio |
| Ollama, local | no quota | no quota | limited by the machine |

Google no longer publishes per-model free quotas in its documentation: they
are shown for each project in Google AI Studio
([Developers Digest](https://www.developersdigest.tech/rate-limits/google), reading the official page on 17 October 2026).

What follows from these figures:

- **Gemini 3.8 Flash on the free tier is not usable for this project.** At
  20 requests a day, it runs two to four audits a day. A Flash-Lite model, a
  paid tier or another provider is needed. To be confirmed in AI Studio.
- **Groq 70B: the daily token cap is the real limit.** At about 6,000 tokens
  per audit, 100,000 tokens a day is about 16 audits. Enough for the live
  demonstration, not for an evaluation on 30 files in one day.
- **Groq 8B instant** allows about 80 audits a day and is the candidate for
  the evaluation runs, with the 70B model kept for the demonstration.

## Interval to set

    interval = max(60 / requests per minute, 60 x tokens per call / tokens per minute)

With about 900 tokens per call (prompt plus answer):

| Provider and model | From requests | From tokens | `LLM_MIN_INTERVAL_SECONDS` |
|---|---|---|---|
| Groq `llama-3.3-70b-versatile` | 2.0 s | 4.5 s | **5** |
| Groq `llama-3.1-8b-instant` | 2.0 s | 9.0 s | **10** |
| Gemini free tier, 5 requests per minute | 12.0 s | negligible | **13** |
| Ollama | none | none | **0** |

An audit of the `no_path` file (9 calls) then takes about 45 s on Groq 70B.
`STEP_DELAY_SECONDS` can be set to 0 when a provider is used: the calls
already pace the interface.

## Measuring on our own key (to do with the real provider)

The table above is computed from published figures. The measured values come
from one command, to run once `backend/.env` holds the provider and the key:

    python eval/measure_llm_limits.py --burst 40

It prints the rate-limit headers returned by the provider, the number of
calls accepted before the first HTTP 429, the exact tokens and the latency of
one audit of each demo file, and the `LLM_MIN_INTERVAL_SECONDS` line to copy
into `backend/.env`. Paste its output here and replace the published figures.

| Measured on | Provider and model | Calls before 429 | Tokens per audit | Seconds per audit | Interval retained |
|---|---|---|---|---|---|
| to do | | | | | |

What the client already does when a limit is hit: HTTP 429 and 5xx answers
are retried twice with a pause; after that the step falls back to its rules,
the audit continues, and the step is marked `rules` in the trail. An audit
never fails because of the provider.
