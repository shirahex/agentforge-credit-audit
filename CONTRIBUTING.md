# Working rules

## Branches

- `main` always runs: tests pass, the interface starts.
- One branch per task, named after the task id in `docs/work-split.pdf`:
  `m3-shap-tool`, `i2-verifier-agent`, `shared-eval-protocol`.
- Branches stay short (one to three days) and are merged through a pull
  request reviewed by the other team member.

## Commits

Short imperative messages prefixed by the area:

```
tools: add DiCE counterfactual generator
graph: add human review interrupt
ui: decision screen with counterfactual cards
```

## Before opening a pull request

```
cd backend && pytest
cd frontend && npm run build
```

## Contracts

`backend/app/schemas.py`, `backend/app/graph/state.py` and the signatures
of the functions in `backend/app/tools` are shared contracts. A change
needs the agreement of both members and, for schemas, the matching update
of `frontend/src/types.ts` in the same pull request.

## Never commit

- API keys or `.env` files (use `.env.example` as the template)
- Raw datasets and trained models (see `ml/data/README.md`)
- `node_modules`, virtual environments, notebook checkpoints
