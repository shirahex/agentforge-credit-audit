# Architecture

## Agents

| Agent | Reads from state | Tools | Writes to state | LLM role | Owner |
|---|---|---|---|---|---|
| Analyste-Dossier | `application` | `validate_application`, `similar_cases` | `analysis`, `warnings` | Analyst note | Marouane |
| Modèle-Scoring | `application` | `score_applicant`, `shap_explain` | `score`, `explanation` | Explanation limited to SHAP factors | Marouane |
| Générateur-Contrefactuels | `application`, `score`, `fairness.reasons`, `cf_plans` | `permitted_moves`, `generate_counterfactuals`, `closest_miss` | `counterfactuals`, `attempts`, `cf_plans` | Search plan: attributes, number of changes, range | Marouane |
| Vérificateur-Équité | `application`, `score`, `counterfactuals` | `sensitive_flip_test` (to add: Fairlearn metrics, plausibility) | `fairness`, filtered `counterfactuals` | To add: verdict wording | Imane |
| Arbitre et Rédacteur | whole state | case store (to add: human interrupt, PDF report) | `decision` | To add: applicant letter | Imane |

Every agent also writes `log`, `reasoning`, `mode` (`llm` or `rules`),
`tool_calls` and `status`, which the API turns into one `AgentEvent`.

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
   fails, when the score is within `BORDERLINE_MARGIN` of the threshold or
   when no way to approval was found.

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
| POST | `/api/audits/{run_id}/review` | Reviewer's decision on an escalated audit |

Runs are kept in memory. Persistence, the LangGraph interrupt behind the
review endpoint and the report download belong to task I4.

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
The interface rebuilds the pipeline, the loop and every result section from
this stream alone (`frontend/src/lib/format.ts`, function `pipelineView`).
