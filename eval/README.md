# Evaluation

Task I6. One command produces every result table:

```
python eval/run_eval.py              # agents on rules, the 200 test files, about one minute
python eval/run_eval.py --limit 40   # quick run
python eval/run_eval.py --llm        # adds the runs that need a language model (provider in backend/.env)
```

## Systems compared

| System | What runs |
|---|---|
| `full` | The five agents with the verification loop |
| `no_loop` | Ablation: the auditor's rejection never sends the file back, one attempt only |
| `no_verifier` | Ablation: no Vérificateur-Équité; what the generator believes valid is delivered, no fairness test |
| `single_pass` | Baseline without agents: one model call, one DiCE call, delivered as is |
| `single_prompt` | Baseline of the work plan: the file through one prompt, no tool. Needs `--llm` |

Every proposal a system delivers is judged again by the same four tools,
whatever the system says about it: valid (decision flips after re-scoring),
actionable (recourse rules), robust (safety margin), plausible (close to real
past applicants). A proposal is sound when it passes all four.

## Tables written to `results/`

| File | Content |
|---|---|
| `RESULTS.md` | Every table below, readable, with the run settings |
| `systems.csv` | One row per system: recourse, soundness of what is delivered, fairness failures caught, escalations, attempts, latency |
| `attempts.csv` | Refusals solved at attempt 1, 2 and 3, with and without the loop |
| `counterfactuals.csv` | Exhaustive search against DiCE: validity, proximity, sparsity, plausibility, actionability rate, coverage |
| `fairness.csv` | Fairlearn group metrics of both model variants, with bootstrap intervals |
| `per_file_<system>.csv` | One row per file (not versioned) |
| `llm_agents.csv`, `llm_files.csv` | With `--llm`: per agent, share of answers rejected by each guard, share of steps falling back to rules, tokens and latency per file |

## Other scripts

- `figures.py`: figures of the result tables, written to `results/figures/` and read in `docs/result-analysis.md`
- `demo_reports.py`: PDF audit report of each of the six demo files, written to `docs/sample-reports/`
- `measure_llm_limits.py`: limits of the configured LLM provider and the matching `LLM_MIN_INTERVAL_SECONDS` (see `docs/llm-limits.md`)

## State on 15 November 2026

Tables 1 to 4 of `RESULTS.md` are final for the agents on rules. The
`single_prompt` baseline and the language model statistics need a provider
key: the code is tested with a scripted model, the numbers are still to be
produced with `--llm`.
