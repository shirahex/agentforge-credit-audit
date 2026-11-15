# Demo scenario

Shared task S2, first version. Order of the six demo files during the
presentation, what to show for each and the point it makes. About eight
minutes. The files are on the "New audit" screen; the PDF of each one is in
`docs/sample-reports/`.

Before starting: backend and interface running, `backend/data/` deleted so
that the history is empty, `STEP_DELAY_SECONDS=0.7` so that each agent is
visible.

| # | File | What to show | Point made |
|---|---|---|---|
| 1 | Approved (GC-0524) | Pipeline: the generator is skipped. Fairness check and group panel. Download the PDF | An approval is audited too. Numbers come from tools: open one step of the trail and read its tool calls |
| 2 | Refused, solved by loan terms (GC-0845) | Two ways to approval with the risk before and after, and the realism of each. The French letter | Specialised agents and tool orchestration. Every proposal was re-scored and checked by the auditor, not by the agent that proposed it |
| 3 | Refused, needs a second attempt (GC-0217) | The red rejection arc. Attempt 1 objections, including "next plan". Attempt 2 follows a different plan and is accepted | The feedback loop is real: a rejection changes what the generator does next |
| 4 | Same as 2, with the amount changed by 150 DM in the form | "Similar files already audited" in the file check, with the link to audit 2 | Memory: a second run retrieves and cites the first one |
| 5 | Decision depends on a sensitive attribute (GC-0130) | Flip test fails. The run waits. Stop and restart the backend, reload the page: the audit is still waiting. Approve as reviewer. The Arbitre turns to done, the letter becomes an approval, the PDF now holds the human decision | Human in the loop on a LangGraph interrupt, and durability: the run survived a restart |
| 6 | Refused, no way to approval (GC-0230) | Three attempts, three different plans, three rejections, escalation. Then the Model page: fairness across groups, and the evaluation table | Retry limit and escalation path. Then the measured value of the design |

Figures to quote at step 6 (`eval/results/RESULTS.md`): with the five agents,
78% of refusals leave with a way to approval that passes every check; without
the loop, 39%; without the auditor, 22% of refused applicants are handed a
proposal that fails a check and none of the 22 decisions depending on a
protected attribute is caught.

If the provider is slow or answers 429 during the presentation, nothing
breaks: the step falls back to rules and the trail says so. Keep
`LLM_PROVIDER=none` as plan B.

Borderline (GC-0538) is kept in reserve: same path as step 5 with a
different escalation rule.
