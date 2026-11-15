# Evaluation

Owner: Imane (task I6), analysis shared.

- `run_eval.py`: runs the agent graph on the test set and writes one row
  per file to `results/` (decision, counterfactual metrics, fairness
  metrics, attempts, tokens, latency)
- Baseline: the same files through a single prompt without the verifier loop
- Ablation: the graph with the verifier loop disabled

Metrics: counterfactual validity, proximity, sparsity, plausibility,
actionability rate, demographic parity difference, equalized odds
difference, flip-test rate, explanation faithfulness, cost per file.
