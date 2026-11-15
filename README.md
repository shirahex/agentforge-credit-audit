# AgentForge Credit Audit

Multi-agent system that audits a credit scoring decision. Five agents score
a loan file, explain the score with exact SHAP values, search for verified
counterfactuals (the smallest realistic changes that turn a refusal into an
approval), test the decision for fairness and close the file or hand it to
a human reviewer.

Project for the Agentic AI module (topic 42), Master IA, Faculté des
Sciences Ben M'Sik, Université Hassan II de Casablanca.

Team AgentForge: Marouane Daouki, Imane Alouani.

![Audit in progress, first attempt rejected by the auditor](docs/screenshots/02-audit-loop.png)

## What it does

```
Analyste-Dossier -> Modèle-Scoring -> Générateur-Contrefactuels -> Vérificateur-Équité -> Arbitre et Rédacteur
                                                 ^                          |
                                                 +--- rejected, new plan ---+
```

| Agent | Role | Tools |
|---|---|---|
| Analyste-Dossier | Checks the file and compares it with past applicants | `validate_application`, `similar_cases` |
| Modèle-Scoring | Scores and explains | `score_applicant`, `shap_explain` |
| Générateur-Contrefactuels | Plans a search and proposes ways to approval | `permitted_moves`, `generate_counterfactuals` (exhaustive search and DiCE), `closest_miss` |
| Vérificateur-Équité | Audits the decision and the proposals, can reject them | `sensitive_flip_test` |
| Arbitre et Rédacteur | Closes the audit or escalates to a human | case store |

Design rules:

- **Numbers come from tools.** The language model plans and words; it never
  produces a score. Its answers pass guards (structure, allowed attributes,
  no number absent from the tool outputs), are retried once with the
  objection, then replaced by rule-based logic. With `LLM_PROVIDER=none`
  every agent runs on rules, so the whole system works without any key.
- **Every counterfactual is re-scored** by the model and checked against
  recourse rules: protected and fixed attributes are never touched, amounts
  and durations only go down, account standing only improves.
- **The loop is real.** When nothing survives the audit, the generator
  receives the objections and must try a different plan: loan terms first,
  then the financial situation, then wider ranges. After three attempts the
  file goes to a human.

## Results on the 200 held-out files

| | |
|---|---|
| Scoring model | LightGBM, monotone constraints, Platt calibration. Test AUC 0.806 (95% interval 0.738 to 0.871), cross-validation AUC 0.788 against 0.767 for logistic regression |
| Refusals that leave with a verified way to approval | 87% (86 of 99) |
| of which solved at attempt 1 / 2 / 3 | 42 / 35 / 9 |
| Files whose decision changes with a protected attribute | 11.0% for the audited model, 0.0% for the variant trained without protected attributes |
| Time per audit, agents on rules | about 100 ms |

Details and figures: [`ml/reports/MODEL_CARD.md`](ml/reports/MODEL_CARD.md).

## Run it

Backend (Python 3.11 or later):

```
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

Interface (Node 20 or later), in a second terminal:

```
cd frontend
npm install
npm run dev
```

The interface opens on http://localhost:5173 and calls the API on port 8000.
The trained model and the prepared data are in the repository, so nothing
has to be downloaded or trained first.

### Language model (optional)

Copy `.env.example` to `backend/.env` and set a provider. Gemini, Groq and a
local Ollama are supported through their OpenAI-compatible endpoints. The
top bar of the interface shows whether the agents run on a model or on rules,
and each step of the audit trail says which one produced it.

### Rebuild data, model and reports

```
pip install -r backend/requirements-ml.txt
python ml/prepare_data.py      # decode the raw file, split train / test
python ml/train.py             # train both variants, calibrate, choose thresholds
python ml/select_samples.py    # pick the six demo files from the test set
python ml/report.py            # figures, model card, audit statistics
```

## Repository layout

| Path | Content | Owner |
|---|---|---|
| `backend/app/domain/` | Attribute definitions, encoder, model runtime | Marouane |
| `backend/app/tools/scoring.py`, `counterfactuals.py`, `analysis.py` | Model, SHAP, counterfactual search, file analysis | Marouane |
| `backend/app/agents/` (first three), `agents/base.py`, `llm/` | Agents, guards, LLM client | Marouane |
| `ml/` | Data, training, reports, notebook | Marouane |
| `frontend/` | React, TypeScript and Tailwind interface | Marouane |
| `backend/app/tools/fairness.py`, `report.py` | Fairlearn metrics, plausibility, PDF report | Imane |
| `backend/app/agents/` (last two) | Vérificateur-Équité, Arbitre et Rédacteur | Imane |
| `backend/app/graph/`, `memory/`, `main.py` | Orchestration, memory, API | Imane |
| `eval/` | Evaluation runner, baseline, ablation | Imane |
| `backend/app/schemas.py` | Shared data contracts | Both |

Files owned by Imane contain working placeholders marked `PLACEHOLDER` and
`TODO`, so the system runs end to end while her parts are built.

## Documents

- `docs/work-split.pdf`: who does what, in detail
- `docs/architecture.md`: agents, state, API and event format
- `ml/reports/MODEL_CARD.md`: model, policy and audit results
- `ml/notebooks/01_eda.ipynb`: exploratory analysis
- `docs/screenshots/`: interface screens
- `CONTRIBUTING.md`: branch, commit and review rules
