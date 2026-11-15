# Architecture

## Agents

| Agent | Input from state | Tools | Output to state | Owner |
|---|---|---|---|---|
| Analyste-Dossier | `application` | validation rules, case store search | `warnings` | Marouane |
| Modèle-Scoring | `application` | `score_applicant`, SHAP explainer | `score` | Marouane |
| Générateur-Contrefactuels | `application`, `score`, previous rejection reasons | `generate_counterfactuals` (DiCE), `check_actionability`, re-scoring | `counterfactuals`, `attempts` | Marouane |
| Vérificateur-Équité | `application`, `score`, `counterfactuals` | Fairlearn metrics, `sensitive_flip_test`, plausibility score | `fairness`, filtered `counterfactuals` | Imane |
| Arbitre et Rédacteur | whole state | human interrupt, `render_report`, case store | `decision` | Imane |

## Routing

1. Analyste-Dossier, then Modèle-Scoring.
2. Refused: Générateur-Contrefactuels, then Vérificateur-Équité.
   Approved: Vérificateur-Équité directly.
3. If the file is refused and no counterfactual survives the audit, back to
   the generator, up to `MAX_CF_ATTEMPTS`.
4. Arbitre et Rédacteur finalises, or escalates to a human when the score is
   within `BORDERLINE_MARGIN` of the threshold, when the flip test fails or
   when no counterfactual was found.

## State

Defined in `backend/app/graph/state.py`. Every value is a Pydantic model
from `backend/app/schemas.py`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness and active LLM provider |
| GET | `/api/samples` | Demo applicant files |
| POST | `/api/audits` | Start an audit, returns `{run_id}` |
| GET | `/api/audits/{run_id}/events` | Server-sent events, one `AgentEvent` per agent step, closed by an `end` event |
| GET | `/api/audits/{run_id}` | Final `AuditDecision` |

Planned: `POST /api/audits/{run_id}/review` (human decision),
`GET /api/audits/{run_id}/report` (PDF).

## Event format

```json
{
  "run_id": "8e450f0448a8",
  "seq": 3,
  "agent": "Vérificateur-Équité",
  "status": "rejected",
  "message": "Audit failed: counterfactual rejected: changes immutable feature(s): age",
  "payload": {"fairness": {}, "counterfactuals": []},
  "ts": "2026-11-15T00:00:00Z"
}
```

`status` is one of `completed`, `rejected`, `escalated`, `finished`, `error`.
The interface draws the timeline and the loop from this stream alone.
