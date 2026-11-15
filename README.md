# AgentForge Credit Audit

Multi-agent system that audits a credit scoring decision: it scores a loan
file, explains the result, searches for verified counterfactuals (the
smallest realistic changes that would turn a refusal into an approval),
checks the decision for fairness and produces an auditable report.

Project for the Agentic AI module (topic 42), Master IA, Faculté des
Sciences Ben M'Sik, Université Hassan II de Casablanca.

Team AgentForge: Marouane Daouki, Imane Alouani.

## Architecture

```
React + Tailwind interface  <--  SSE event stream  --  FastAPI
                                                         |
                                                    LangGraph graph
                                                         |
  Analyste-Dossier -> Modèle-Scoring -> Générateur-Contrefactuels -> Vérificateur-Équité -> Arbitre et Rédacteur
                                                 ^                          |
                                                 +---- rejected, retry -----+
```

Agents never produce numbers themselves. Scores, explanations,
counterfactuals and fairness metrics come from deterministic tools in
`backend/app/tools`.

## Repository layout

| Path | Content | Owner |
|---|---|---|
| `backend/app/schemas.py` | Shared data contracts | Both |
| `backend/app/tools/scoring.py`, `counterfactuals.py` | Model, SHAP, DiCE, actionability | Marouane |
| `backend/app/tools/fairness.py`, `report.py` | Fairlearn metrics, flip test, PDF report | Imane |
| `backend/app/agents/` | One file per agent (owner in each file header) | Split |
| `backend/app/graph/` | State, routing, loops, human checkpoint | Imane |
| `backend/app/main.py`, `llm/`, `memory/` | API, LLM wrapper, case store | Imane |
| `ml/` | Data preparation, training, notebooks, saved models | Marouane |
| `frontend/` | React + TypeScript + Tailwind interface | Marouane |
| `eval/` | Evaluation runner, baseline, result tables | Imane |
| `docs/` | Architecture notes, work split, blueprints | Both |

## Current state

The skeleton runs end to end with placeholder tools: a hand-written
scoring formula and fixed counterfactual candidates. Each placeholder is
marked `PLACEHOLDER` or `TODO` with the task that replaces it. No LLM key
is needed yet (`LLM_PROVIDER=none`).

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

Frontend (Node 20 or later), in a second terminal:

```
cd frontend
npm install
npm run dev
```

The interface opens on http://localhost:5173 and calls the API on port 8000.

## Documents

- `docs/work-split.pdf`: detailed assignment of tasks
- `docs/architecture.md`: agents, state, API and event format
- `docs/pipeline-blueprints.pdf`: initial blueprint of the topic
- `CONTRIBUTING.md`: branch, commit and review rules
