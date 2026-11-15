# Architecture

## Agents

| Agent | Reads from state | Tools | Writes to state | LLM role | Owner |
|---|---|---|---|---|---|
| Analyste-Dossier | `application` | `validate_application`, `similar_cases`, `past_audits` | `analysis`, `warnings` | Analyst note, citing a similar past audit | Marouane |
| Modèle-Scoring | `application` | `score_applicant`, `shap_explain` | `score`, `explanation` | Explanation limited to SHAP factors | Marouane |
| Générateur-Contrefactuels | `application`, `score`, `fairness.reasons`, `cf_plans` | `permitted_moves`, `generate_counterfactuals`, `closest_miss` | `counterfactuals`, `attempts`, `cf_plans` | Search plan: attributes, number of changes, range | Marouane |
| Vérificateur-Équité | `application`, `score`, `counterfactuals` | `sensitive_flip_test`, `group_fairness_metrics`, `group_context`, `check_actionability`, `rescore_candidates`, `plausibility_score` | `fairness`, filtered `counterfactuals` | Wording of the verdict; the outcome is decided by the tools | Imane |
| Arbitre et Rédacteur | whole state | `past_audits`, `escalation_rules`; at closing `render_report`, `case_store.add` | `decision` (letter, review, report) | Applicant letter in French | Imane |

Every agent also writes `log`, `reasoning`, `mode` (`llm` or `rules`),
`tool_calls` and `status`. The graph wraps each agent (`_step` in
`graph/build.py`) and turns these into one trail record, appended to the
state under `trail`. The `AgentEvent` of the API, the JSONL trace and the PDF
report are all built from these records.

## Audit of the proposals (Vérificateur-Équité)

A proposal survives when it passes four checks, each run by the auditor
itself whatever flags the proposal arrived with:

| Check | Tool | Objection sent back when it fails |
|---|---|---|
| Recourse rules | `check_actionability` | the rule broken, for example "cuts duration by more than 60%" |
| Decision really flips | `rescore_candidates` (fresh model call) | "every permitted change together only reaches 33%, above the threshold" |
| Safety margin | same call, `ROBUST_MARGIN` | "flips the decision without a safety margin" |
| Realism | `plausibility_score` | "unrealistic file, too far from past applicants" |

Plausibility: mean Gower distance between the modified file and its 5
nearest training files, on the non-protected attributes. The same distance
is computed for every training file (leave-one-out); a modified file beyond
the 95th percentile is an outlier. It is still accepted when the changes
moved it by less than `PLAUSIBILITY_SLACK`, so an applicant who is already
unusual is not blamed for it.

When nothing survives, a last objection starting with `next plan:` says what
to change (add the financial situation, prefer smaller changes, widen the
ranges). Objections stay under 120 characters: the generator's next plan is
built from them.

Fairness has two levels. The flip test concerns this file and can send it to
a person. The Fairlearn group metrics (selection rate, demographic parity
difference and ratio, equalized odds difference, by sex, age band and
foreign-worker status, for both model variants, with bootstrap intervals)
describe the model on the 200 test files; they are recorded with the
position of the applicant's own groups, as notes for the reviewer, and never
reject a proposal.

## Applicant letter (Arbitre et Rédacteur)

Written in French from a dictionary of facts built by tools
(`letter_facts`): request, decision, risk and threshold, SHAP factors on
non-protected attributes, verified ways to approval with their risk. The LLM
letter is refused when its decision differs from the audit, when it names a
protected attribute, when it omits the ways to approval, or when it quotes a
number absent from the facts; a French template built from the same facts
replaces it. The letter of an escalated file is a draft until the reviewer
decides, then it is rewritten for the final outcome.

## Guarded LLM answers

`backend/app/agents/base.py`, function `guarded_answer`:

1. the agent sends the tool outputs as JSON facts and asks for a JSON object;
2. the answer is validated against a Pydantic model;
3. an agent-specific check runs (cited factors must be SHAP factors; planned
   attributes must be actionable; a failed plan cannot be replayed);
4. the number guard rejects any figure that is not in the facts;
5. on failure the objection is sent back once; a second failure, a network
   error or `LLM_PROVIDER=none` switches the step to its rule-based logic.

## Routing

1. Analyste-Dossier, then Modèle-Scoring.
2. Refused: Générateur-Contrefactuels, then Vérificateur-Équité.
   Approved: Vérificateur-Équité directly.
3. Refused and nothing survives the audit: back to the generator with the
   objections, up to `MAX_CF_ATTEMPTS` (3).
4. Arbitre et Rédacteur closes the audit, or escalates when the flip test
   fails, when the score is within `BORDERLINE_MARGIN` of the threshold,
   when no way to approval was found, or when a near-identical past file
   received the opposite outcome.
5. Escalated: the graph stops on a LangGraph interrupt (`revue_humaine`).
   The reviewer's answer resumes it; the letter is rewritten for the final
   outcome, the report is issued again and the case is stored.

## Durability and memory

| What | Where | Role |
|---|---|---|
| Checkpoints | `data/checkpoints.sqlite` (`memory/checkpointer.py`) | State saved after every step. A run cut by a restart resumes from it without running finished steps again; a run waiting for its reviewer stays there |
| Runs and events | `data/audit.sqlite`, tables `runs` and `events` (`memory/run_store.py`) | History, event stream and review state served by the API |
| Case store | `data/audit.sqlite`, table `cases` (`memory/case_store.py`) | Closed audits. Similarity is 1 minus the Gower distance on non-protected attributes; cited from 0.85, same case from 0.97 |
| Trace | `data/traces/<run_id>.jsonl` (`graph/trace.py`) | One line per step: tool calls with arguments, results and durations, LLM calls and tokens, outcome of each guard. Read by the evaluation |
| Reports | `data/reports/<report_id>.pdf` (`tools/report.py`) | PDF audit report; rebuilt from the trace if the file is missing |

Two graphs are compiled from the same nodes. `graph` has no checkpointer and
no interrupt, and no side effect: one `invoke` returns the final state
(tests, model report, evaluation). `durable_graph()` adds both and is run by
`graph/runner.py` for the API. A run writes to the stores only when the state
carries a `run_id`. When the API starts, runs left in the `running` state
are resumed.

## Counterfactual search

- `permitted_moves` lists, for one applicant, the values each actionable
  attribute may take: amount and duration only decrease (never below 55% of
  the request, 40% with wider ranges), savings and account standing only
  improve, a guarantor can be added, running credits and other instalment
  plans can be closed.
- `exhaustive_search` scores every combination of up to three moves in one
  model call and keeps the cheapest valid combination per set of attributes.
- `dice_search` runs DiCE on the same attributes as an independent source.
  DiCE ignores direction rules, so its proposals are filtered by
  `check_actionability`, which gives the auditor real candidates to reject.
- A candidate is `valid` when the re-scored decision flips, `robust` when it
  clears the threshold by `ROBUST_MARGIN`.

The model is trained with monotone constraints on duration, amount and
instalment rate, so a smaller or shorter request can never score worse.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Model version, threshold, LLM status and usage |
| GET | `/api/schema` | Attribute labels, options and ranges for the form |
| GET | `/api/samples` | Six demo files from the test set |
| GET | `/api/model` | Model card data, curves and audit statistics |
| POST | `/api/audits` | Start an audit, returns `{run_id}` |
| GET | `/api/audits` | History |
| GET | `/api/audits/{run_id}` | Application, events, decision, review |
| GET | `/api/audits/{run_id}/events` | Server-sent events, closed by an `end` event |
| POST | `/api/audits/{run_id}/review` | Reviewer's decision: resumes the interrupted graph. 409 when the audit is running, was not escalated or is already reviewed |
| GET | `/api/audits/{run_id}/report` | PDF audit report |
| GET | `/api/audits/{run_id}/letter` | Applicant letter, plain text |
| GET | `/api/audits/{run_id}/trace` | JSONL trace |
| GET | `/api/fairness` | Fairlearn group metrics of both model variants |

A run has a `status`: `running`, `awaiting_review`, `finished` or `error`.
`done` is true as soon as it is not running, so the interface closes the
event stream and shows the review form for an escalated audit.

## Event format

```json
{
  "run_id": "8e450f0448a8", "seq": 3,
  "agent": "Vérificateur-Équité", "node": "verificateur_equite",
  "status": "rejected",
  "message": "Nothing survives the audit: every permitted change together only reaches 33%, above the threshold.",
  "reasoning": "...", "mode": "rules",
  "tool_calls": [{"name": "sensitive_flip_test", "arguments": {}, "result": "decision unchanged", "duration_ms": 1.2}],
  "payload": {"fairness": {}, "counterfactuals": []},
  "ts": "2026-11-15T00:00:00Z"
}
```

`status` is one of `completed`, `rejected`, `escalated`, `finished`, `error`.
The step that closes a reviewed audit is reported under `arbitre_redacteur`,
so the interface keeps five nodes.
The interface rebuilds the pipeline, the loop and every result section from
this stream alone (`frontend/src/lib/format.ts`, function `pipelineView`).
