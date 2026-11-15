# Result analysis

Shared task S3, first version. Reading of the evaluation tables
(`eval/results/RESULTS.md`), with the figures of `eval/results/figures/` and
the limits of what they show. All figures: 200 held-out files, 99 of them
refused by the model, agents on rules. Section 6 reports the runs with a
language model, on 12 files.

## 1. The question

The module excludes "a predictive model behind an API". The evaluation
therefore asks what the agents add to the model: the same files go through
the full system, through the system with one part removed, and through a
script without agents. Every proposal a system hands to an applicant is
judged again by the same four tools, whatever the system claims: it must flip
the decision when re-scored, respect the recourse rules, clear the threshold
with a margin, and stay close to real past applicants. A proposal that
passes all four is called sound.

## 2. What a refused applicant receives

![What a refused applicant receives](../eval/results/figures/systems.png)

| System | Refusals with a sound way | Refusals handed an unsound proposal | Sensitive dependence caught |
|---|---|---|---|
| Five agents with the loop | 78% (77 of 99) | 0% | 22 of 22 |
| Without the rejection loop | 39% (39 of 99) | 0% | 22 of 22 |
| Without the auditor agent | 39% | 22% | 0 of 22 |
| Model + DiCE, no agents | 35% | 100% | 0 of 22 |

Three results follow.

**The loop doubles the recourse.** With one attempt, 39 refusals get a way to
approval. With the loop, 77 do. The 38 additional files are those where loan
terms alone were not enough and the auditor's objection sent the generator
to the financial situation (34 files at the second attempt) or to wider
ranges (4 at the third).

![Where the rejection loop pays](../eval/results/figures/attempts.png)

**The auditor is what makes the proposals safe to hand over.** Without it,
the generator's own flags let through proposals that flip the decision with
no margin (23% of what it delivers) or that describe a file unlike any real
applicant (16%). One refused applicant in five (22%) would receive at least
one such proposal. And none of the 22 files whose decision changes with sex
or foreign-worker status would be seen by anyone: they would be closed like
the others.

**A library call is not a recourse system.** DiCE alone produces 395
proposals; 12% are sound. It ignores the recourse rules: 85% of its proposals
ask for something the applicant cannot do. Half of those cut the amount or
the duration by more than 60%, a quarter move the account or the savings to
a state that cannot be reached, a fifth ask for a larger or longer loan. So
every refused applicant receives at least one unusable proposal. This is the
baseline "without agents": it is the same model and the same library the
agents use, without the plan, the rules and the audit.

How to read the 100% of the first two rows: the four checks are the ones the
auditor applies, so its output passes them by construction. The evidence is
in the other columns: coverage (78% against 39%), and what the systems
without the auditor deliver.

## 3. Cost of the verification

- Time: 104 ms per file for the full system against 49 ms for the script
  without agents. The loop accounts for most of the difference.
- Human workload: 48 files of 200 go to a reviewer. 22 because the decision
  depends on a sensitive attribute, 22 because no way to approval exists,
  4 because the score is on the threshold. Without the loop, 82 files would
  go to a reviewer: the loop also halves the human workload.
- Recourse lost to realism: before the plausibility check, 86 of 99 refusals
  had a way to approval; with it, 77. Nine applicants only had proposals
  that no longer looked like a real file. We count this as a gain in
  honesty, not as a loss, but it is a choice: the limit (95th percentile of
  real files) is a parameter.

## 4. The two generators

![Counterfactual generators](../eval/results/figures/generators.png)

| | Exhaustive search | DiCE |
|---|---|---|
| Valid after re-scoring | 100% | 100% |
| Actionability rate | 100% | 15% |
| Robust | 60% | 86% |
| Plausible | 85% | 89% |
| Sound | 51% | 12% |
| Proximity (Gower distance, lower is closer) | 0.092 | 0.084 |
| Sparsity (attributes changed) | 2.2 | 2.0 |
| Refusals with a sound proposal | 67% | 35% |
| Time per file | 2 ms | 94 ms |

The exhaustive search is valid and actionable by construction: it only
enumerates permitted moves and only returns combinations it scored under the
threshold. It looks for the cheapest change, so 40% of its proposals land
just under the threshold without a margin; the auditor removes those. DiCE
overshoots (86% robust) but breaks the rules. The two are complementary,
which is why the generator uses both and the auditor filters both. The
exhaustive search is also about 45 times faster.

## 5. Fairness

![Approval rate by group](../eval/results/figures/fairness.png)

| Attribute | Audited model | Model without protected attributes |
|---|---|---|
| Sex: approval gap (demographic parity difference) | 9 points (95% interval 1 to 24) | 1 point (0 to 18) |
| Age band: approval gap | 18 points (5 to 39) | 11 points (3 to 32) |
| Age band: equalized odds difference | 22 points | 20 points |
| Files whose own decision flips with a protected attribute | 11.0% | 0.0% |

- Removing the protected attributes removes the gap between women and men.
- It does not remove the gap for applicants aged 18 to 25: 11 points remain,
  with no access to age. The model rebuilds part of it from correlated
  attributes (time in employment, housing, property). "Fairness through
  unawareness" is therefore not enough here, and this is the reason for
  keeping both levels of test: the flip test says nothing about proxies.
- The foreign-worker comparison is not interpreted: 6 non-foreign files.
- All intervals are wide. With 200 files, a gap of 9 points between women
  and men is compatible with almost no gap. We report it, we do not claim it.

## 6. Runs with a language model

Groq free plan, `openai/gpt-oss-20b`, the first 12 test files (4 refused by
the model), 15 November 2026. Twelve files is a small sample: the figures
below show how the system behaves, they are not precise rates.

### The five agents with the model

| Agent | Steps | Written by the model | Answers | Accepted | Rejected: invented number | Fallback to rules | Tokens per step |
|---|---|---|---|---|---|---|---|
| Analyste-Dossier | 12 | 12 | 16 | 75% | 25% | 0% | 828 |
| Modèle-Scoring | 12 | 12 | 13 | 92% | 8% | 0% | 1,159 |
| Générateur-Contrefactuels | 7 | 7 | 7 | 100% | 0% | 0% | 1,399 |
| Vérificateur-Équité | 15 | 15 | 15 | 100% | 0% | 0% | 825 |
| Arbitre et Rédacteur | 12 | 12 | 12 | 100% | 0% | 0% | 1,978 |

- **The number guard is not decorative.** 5 answers out of 63 (8%) quoted a
  number that no tool had produced: 4 analyst notes and 1 score explanation.
  Each was sent back with the objection and the second answer passed. No
  answer was rejected for its structure or by an agent-specific check.
- **No step fell back to rules** on these 12 files (58 steps). On the six
  demo files measured separately, 1 step of 38 did.
- **Decisions and escalations are unchanged.** They come from tools, so they
  are identical to the run on rules on all 12 files, and the same 3 refusals
  leave with a way to approval.
- **The planner does change the search.** The model's plans name fewer
  attributes than the fixed ladder: one refusal is solved at the first
  attempt instead of the second, and the 3 refusals receive 3 ways to
  approval in total instead of 8. Fewer, more targeted proposals; whether
  that is better for the applicant is open.
- **Cost:** 5.3 calls and about 5,800 tokens per file (2,550 prompt, 3,260
  completion, reasoning included), 73 s per file with a 12 s pause between
  calls. On rules the same audit takes 0.1 s.

### The baseline through a single prompt

The same 12 files, one prompt each, no tool: the model must give the
decision, the probability, three factors and up to three sets of changes.

| | Single prompt | Five agents |
|---|---|---|
| Decision equal to the scoring model's | 8 of 12 | 12 of 12 (the model's decision is the tool's output) |
| Files approved by the scoring model that it refuses | 4 of 8 | 0 |
| Mean error on the default probability | 17 points | 0 |
| Named factors that are among the 6 SHAP factors | 64% | 100% (enforced by a guard) |
| Proposals delivered | 24 | 3 |
| of which respect the recourse rules | 0 of 24 | 3 of 3 |
| of which pass every check | 0 of 24 | 3 of 3 |
| Decisions depending on a protected attribute caught | 0 of 2 | 2 of 2 |

Without tools, the language model does not reproduce the scoring model: it
answers a probability between 18% and 35% whatever the file (the true values
range from 7% to 80%), refuses half of the files the scoring model approves,
and none of its 24 proposals is something the applicant may do under the
recourse rules. 15 of them would flip the decision if applied, which makes
them more dangerous than useless: they read as valid advice. This is the
clearest argument for the design rule "numbers come from tools".

## 7. Limits

1. **Small sample with the language model.** Tables 1 to 4 use the agents
   on rules on 200 files. The runs with a model cover 12 files and one model
   (`openai/gpt-oss-20b`), because of the free quota. A second model (a local
   Mistral or Phi through Ollama) and 30 files or more would turn the
   observations of section 6 into rates.
2. **The judge and the auditor share their tools.** Soundness is measured
   with the checks the auditor applies. An independent criterion (for
   example a second model, or a human rating of a sample of proposals) would
   make the 100% a result instead of a property.
3. **Small, old data.** 1,000 files from one German bank in the 1990s, 200
   for the test. Fairness intervals are wide, and the model's accuracy
   advantage over a logistic regression is only established in
   cross-validation.
4. **Counterfactuals are about the model.** A way to approval says what the
   model would decide for the modified file. It is not a causal claim that
   the applicant would repay.
5. **Plausibility is a distance.** It compares a modified file with past
   files; it does not know that some combinations are impossible for other
   reasons (a guarantor may not exist). The reviewer and the applicant
   remain the judges of feasibility.
6. **The reviewer is not evaluated.** 48 files go to a person; the quality
   and the consistency of human decisions are outside this evaluation. The
   case store flags a near-identical file with the opposite outcome, which
   is a first control.
