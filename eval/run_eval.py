"""Evaluation harness (task I6): what does the multi-agent design bring?

    python eval/run_eval.py                  every table, agents on rules, the 200 test files
    python eval/run_eval.py --limit 40       quick run on the first 40 files
    python eval/run_eval.py --llm            adds the runs that need a language model (see below)

The same held-out files go through five systems:

    full            the five agents with the verification loop (the system as delivered)
    no_loop         ablation: same agents, but the auditor's rejection never sends the file back;
                    one attempt only
    no_verifier     ablation: no Vérificateur-Équité at all; what the generator believes valid
                    is handed to the applicant, and no fairness test runs
    single_pass     baseline without agents: one model call and one DiCE call, delivered as is
    single_prompt   baseline of the work plan: the file through ONE prompt, no tool; the language
                    model must give the decision, the probability, the factors and the changes.
                    Needs a provider (--llm); it is reported as "not run" otherwise.

Nothing a system says about its own proposals is trusted here. Every
delivered proposal is judged again by the same four tools, whatever system
produced it:

    valid       the model decision flips when the modified file is re-scored
    actionable  recourse rules respected (check_actionability)
    robust      the new risk clears the threshold by ROBUST_MARGIN
    plausible   the modified file stays close to real past applicants (plausibility_score)
    sound       all four at once: a proposal that can be given to an applicant

Tables written to eval/results/ (CSV), plus RESULTS.md with all of them:

    systems.csv            one row per system: recourse, soundness of what is delivered,
                           fairness failures caught, escalations, attempts, latency
    counterfactuals.csv    exhaustive search against DiCE: validity, proximity, sparsity,
                           plausibility, actionability rate, coverage
    fairness.csv           Fairlearn group metrics of both model variants
    attempts.csv           where the loop pays: refusals solved at attempt 1, 2 and 3
    per_file_<system>.csv  one row per file and per system
    llm_agents.csv, llm_files.csv   (--llm) per agent: share of answers rejected by each guard,
                           share of steps falling back to rules, tokens and latency per file
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
# The evaluation never writes to the stores of the application, and never reads past audits from them.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="agentforge-eval-")
os.environ.setdefault("TQDM_DISABLE", "1")

import pandas as pd  # noqa: E402

from app import config  # noqa: E402
from app.agents import analyste_dossier, generateur_contrefactuels, modele_scoring  # noqa: E402
from app.domain.features import ACTIONABLE, BY_NAME, FEATURES  # noqa: E402
from app.graph import trace  # noqa: E402
from app.graph.build import build_graph, graph  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.schemas import Counterfactual, LoanApplication  # noqa: E402
from app.tools import scoring  # noqa: E402
from app.tools.counterfactuals import check_actionability, dice_search, exhaustive_search  # noqa: E402
from app.tools.fairness import (gower_distance, group_fairness_comparison, plausibility_score,  # noqa: E402
                                sensitive_flip_test)

RESULTS = ROOT / "eval" / "results"
SYSTEMS = {
    "full": "Five agents with the verification loop",
    "no_loop": "Ablation: no rejection loop (one attempt)",
    "no_verifier": "Ablation: no auditor agent",
    "single_pass": "Baseline: model + DiCE, no agents",
    "single_prompt": "Baseline: one prompt, no tools",
}


# --------------------------------------------------------------------------- judging a proposal
def assess(app: LoanApplication, changes: dict[str, Any]) -> dict[str, Any]:
    """Independent judgement of one proposal, the same for every system."""
    base = app.features()
    known = bool(changes) and all(k in BY_NAME for k in changes)
    try:
        modified = {**base, **changes}
        LoanApplication(applicant_id=app.applicant_id, **modified)  # values must exist in the attribute dictionary
        well_formed = known
    except Exception:
        well_formed = False
    if not well_formed:
        return {"well_formed": False, "valid": False, "actionable": False, "robust": False, "plausible": False,
                "sound": False, "proximity": None, "sparsity": len(changes), "plausibility": None, "new_probability": None}
    thr = scoring.threshold()
    p = float(scoring.probabilities([modified])[0])
    actionable = check_actionability(app, changes)[0]
    plaus = plausibility_score(app, changes)
    valid, robust = p < thr, p <= thr - config.ROBUST_MARGIN
    return {"well_formed": True, "valid": valid, "actionable": actionable, "robust": robust, "plausible": plaus.plausible,
            "sound": valid and actionable and robust and plaus.plausible,
            "proximity": gower_distance(base, modified), "sparsity": len(changes), "plausibility": plaus.score,
            "new_probability": p}


def _changes(cf: Counterfactual) -> dict[str, Any]:
    return {c.feature: c.to_value for c in cf.changes}


def _row(app: LoanApplication, defaulted: int, decision: str, p: float | None, proposals: list[dict[str, Any]],
         attempts: int, escalated: bool, flip_caught: bool, ms: float, extra: dict | None = None) -> dict[str, Any]:
    truth = scoring.score_applicant(app, explain=False)
    flip_ok, _ = sensitive_flip_test(app)
    judged = [assess(app, c) for c in proposals]
    n = len(judged)
    return {
        "applicant_id": app.applicant_id, "defaulted": defaulted,
        "model_decision": truth.decision, "model_probability": round(truth.default_probability, 4),
        "decision": decision, "probability": None if p is None else round(p, 4),
        "decision_agrees": decision == truth.decision,
        "attempts": attempts, "escalated": escalated,
        "depends_on_sensitive_attribute": not flip_ok, "sensitive_dependence_caught": bool(flip_caught and not flip_ok),
        "proposals": n,
        "proposals_valid": sum(j["valid"] for j in judged), "proposals_actionable": sum(j["actionable"] for j in judged),
        "proposals_robust": sum(j["robust"] for j in judged), "proposals_plausible": sum(j["plausible"] for j in judged),
        "proposals_sound": sum(j["sound"] for j in judged),
        "has_sound_proposal": any(j["sound"] for j in judged),
        "has_unsound_proposal": any(not j["sound"] for j in judged),
        "mean_proximity": _mean([j["proximity"] for j in judged]), "mean_sparsity": _mean([j["sparsity"] for j in judged]),
        "mean_plausibility": _mean([j["plausibility"] for j in judged]),
        "ms": round(ms, 1), **(extra or {}),
    }


def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(mean(values), 4) if values else None


# --------------------------------------------------------------------------- the five systems
def run_graph(compiled) -> Callable[[LoanApplication, int], dict]:
    def run(app: LoanApplication, defaulted: int) -> dict:
        started = time.perf_counter()
        out = compiled.invoke({"application": app})
        ms = (time.perf_counter() - started) * 1000
        d = out["decision"]
        totals = trace.summarise(out["trail"])
        return _row(app, defaulted, d.decision, d.default_probability, [_changes(c) for c in d.counterfactuals],
                    d.attempts, d.escalated, not out["fairness"].flip_test_passed, ms,
                    {"llm_calls": totals["llm_calls"], "tokens": totals["prompt_tokens"] + totals["completion_tokens"],
                     "tool_calls": totals["tool_calls"], "_trail": out["trail"]})
    return run


def run_no_verifier(app: LoanApplication, defaulted: int) -> dict:
    """Analyst, scoring and one generator attempt. Its own flags are taken at face value; no audit."""
    started = time.perf_counter()
    state: dict = {"application": app}
    state |= analyste_dossier.run(state)
    state |= modele_scoring.run(state)
    proposals: list[dict] = []
    attempts = 0
    if state["score"].decision == "refused":
        state |= generateur_contrefactuels.run(state)
        attempts = 1
        proposals = [_changes(c) for c in state["counterfactuals"] if c.valid and c.actionable]
    ms = (time.perf_counter() - started) * 1000
    return _row(app, defaulted, state["score"].decision, state["score"].default_probability, proposals, attempts,
                False, False, ms)


def run_single_pass(app: LoanApplication, defaulted: int) -> dict:
    """What a script without agents does: score the file, call DiCE once, return its output."""
    started = time.perf_counter()
    score = scoring.score_applicant(app)
    proposals = [_changes(c) for c in dice_search(app, ACTIONABLE)] if score.decision == "refused" else []
    ms = (time.perf_counter() - started) * 1000
    return _row(app, defaulted, score.decision, score.default_probability, proposals, 1 if proposals else 0, False,
                False, ms)


SINGLE_PROMPT = """You are a credit analyst. You receive one loan application (JSON), the dictionary of its attributes
with their allowed values, and the refusal threshold on the probability of default. No tool is available.
1. Estimate the probability that the applicant defaults (between 0 and 1) and decide: "refused" when it is at
   or above the threshold, "approved" otherwise.
2. Name the three attributes that weigh most in your estimate.
3. If the file is refused, propose up to three sets of changes the applicant could make to be approved. Each set
   maps attribute names to new values taken from the dictionary. Never change age, sex or foreign_worker.
Answer with a JSON object:
{"decision": "approved" or "refused", "default_probability": 0.0, "factors": ["attribute", ...],
 "proposals": [{"attribute": new_value, ...}, ...]}"""


def run_single_prompt(app: LoanApplication, defaulted: int) -> dict | None:
    dictionary = {f.name: ([c[0] for c in f.categories] if f.kind == "categorical" else
                           [True, False] if f.kind == "boolean" else {"min": f.minimum, "max": f.maximum})
                  for f in FEATURES}
    user = ("Application:\n" + app.model_dump_json(exclude={"applicant_id"}) + "\n\nAttribute dictionary:\n"
            + str(dictionary) + f"\n\nRefusal threshold: {scoring.threshold()}")
    before = (llm.USAGE.calls, llm.USAGE.prompt_tokens + llm.USAGE.completion_tokens)
    started = time.perf_counter()
    answer = llm.ask_json(SINGLE_PROMPT, user, max_tokens=700)
    ms = (time.perf_counter() - started) * 1000
    if not isinstance(answer, dict) or answer.get("decision") not in ("approved", "refused"):
        return None  # counted as an unusable answer
    try:
        p = min(1.0, max(0.0, float(answer.get("default_probability"))))
    except (TypeError, ValueError):
        p = None
    proposals = [c for c in (answer.get("proposals") or []) if isinstance(c, dict)][:3] if answer["decision"] == "refused" else []
    factors = [f for f in (answer.get("factors") or []) if isinstance(f, str)][:3]
    shap = {f.feature for f in scoring.explain_applicant(app)[0]}
    row = _row(app, defaulted, answer["decision"], p, proposals, 1 if proposals else 0, False, False, ms, {
        "llm_calls": llm.USAGE.calls - before[0],
        "tokens": llm.USAGE.prompt_tokens + llm.USAGE.completion_tokens - before[1],
        "factors_in_shap_top6": round(sum(f in shap for f in factors) / len(factors), 4) if factors else None,
    })
    row["probability_error"] = None if p is None else round(abs(p - row["model_probability"]), 4)
    return row


# --------------------------------------------------------------------------- tables
def system_table(name: str, rows: list[dict], unusable: int = 0) -> dict[str, Any]:
    refused = [r for r in rows if r["model_decision"] == "refused"]
    told_refused = [r for r in rows if r["decision"] == "refused"]
    delivered = sum(r["proposals"] for r in rows)
    share = lambda key: round(sum(r[key] for r in rows) / delivered, 4) if delivered else None  # noqa: E731
    sensitive = [r for r in rows if r["depends_on_sensitive_attribute"]]
    n_ref = max(len(refused), 1)
    return {
        "system": name, "description": SYSTEMS[name], "files": len(rows), "unusable_answers": unusable,
        "decision_agreement": round(mean(r["decision_agrees"] for r in rows), 4) if rows else None,
        "refusals": len(told_refused),
        "proposals_delivered": delivered,
        "valid": share("proposals_valid"), "actionable": share("proposals_actionable"),
        "robust": share("proposals_robust"), "plausible": share("proposals_plausible"),
        "sound": share("proposals_sound"),
        # of the files the model refuses: leaves with at least one proposal that survives every check
        "refusals_with_sound_way": round(sum(r["has_sound_proposal"] for r in refused) / n_ref, 4),
        # of the files the model refuses: handed at least one proposal that fails a check
        "refusals_given_unsound_proposal": round(sum(r["has_unsound_proposal"] for r in refused) / n_ref, 4),
        "sensitive_dependent_files": len(sensitive),
        "sensitive_dependence_caught": sum(r["sensitive_dependence_caught"] for r in rows),
        "escalated_to_human": sum(r["escalated"] for r in rows),
        "mean_attempts_per_refusal": round(mean(r["attempts"] for r in refused), 2) if refused else None,
        "mean_sparsity": _mean([r["mean_sparsity"] for r in rows]),
        "mean_proximity": _mean([r["mean_proximity"] for r in rows]),
        "mean_plausibility": _mean([r["mean_plausibility"] for r in rows]),
        "ms_per_file": round(mean(r["ms"] for r in rows), 1) if rows else None,
        "llm_calls_per_file": round(mean(r.get("llm_calls", 0) for r in rows), 2) if rows else None,
        "tokens_per_file": round(mean(r.get("tokens", 0) for r in rows), 1) if rows else None,
    }


def generator_table(files: list[tuple[LoanApplication, int]]) -> list[dict]:
    """Exhaustive search against DiCE on the refused files, each judged by the same tools."""
    refused = [app for app, _ in files if scoring.score_applicant(app, explain=False).decision == "refused"]
    out = []
    generators = {
        "exhaustive": lambda app: exhaustive_search(app, None, 3, False),
        "dice": lambda app: dice_search(app, None, 4),
    }
    for name, generate in generators.items():
        judged, covered, sound_covered, seconds = [], 0, 0, 0.0
        for app in refused:
            started = time.perf_counter()
            found = generate(app)
            seconds += time.perf_counter() - started
            mine = [assess(app, _changes(c)) for c in found]
            judged += mine
            covered += any(j["valid"] and j["actionable"] for j in mine)
            sound_covered += any(j["sound"] for j in mine)
        n = max(len(judged), 1)
        out.append({
            "generator": name, "refused_files": len(refused), "candidates": len(judged),
            "candidates_per_file": round(len(judged) / max(len(refused), 1), 2),
            "validity": round(sum(j["valid"] for j in judged) / n, 4),
            "actionability_rate": round(sum(j["actionable"] for j in judged) / n, 4),
            "robust": round(sum(j["robust"] for j in judged) / n, 4),
            "plausible": round(sum(j["plausible"] for j in judged) / n, 4),
            "sound": round(sum(j["sound"] for j in judged) / n, 4),
            "proximity": _mean([j["proximity"] for j in judged]),
            "sparsity": _mean([j["sparsity"] for j in judged]),
            "plausibility": _mean([j["plausibility"] for j in judged]),
            "coverage_valid_actionable": round(covered / max(len(refused), 1), 4),
            "coverage_sound": round(sound_covered / max(len(refused), 1), 4),
            "ms_per_file": round(seconds / max(len(refused), 1) * 1000, 1),
        })
    return out


def fairness_table() -> list[dict]:
    comparison = group_fairness_comparison()
    rows = []
    for variant in ("full", "unaware"):
        report = comparison[variant]
        for attribute, r in report["attributes"].items():
            ci = r["ci95"]
            for group, g in r["groups"].items():
                rows.append({"model": variant, "attribute": attribute, "row": "group", "group": group, "files": g["n"],
                             "selection_rate": g["selection_rate"], "true_positive_rate": g["true_positive_rate"],
                             "false_positive_rate": g["false_positive_rate"], "small_sample": g["small_sample"]})
            rows.append({"model": variant, "attribute": attribute, "row": "difference", "group": "",
                         "files": report["files"],
                         "demographic_parity_difference": r["demographic_parity_difference"],
                         "dp_ci95_low": ci["demographic_parity_difference"][0],
                         "dp_ci95_high": ci["demographic_parity_difference"][1],
                         "demographic_parity_ratio": r["demographic_parity_ratio"],
                         "equalized_odds_difference": r["equalized_odds_difference"],
                         "eo_ci95_low": ci["equalized_odds_difference"][0],
                         "eo_ci95_high": ci["equalized_odds_difference"][1],
                         "alert": r["alert"], "four_fifths_ok": r["four_fifths_ok"]})
    return rows


def attempts_table(per_system: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for name in ("full", "no_loop"):
        refused = [r for r in per_system.get(name, []) if r["model_decision"] == "refused"]
        solved = Counter(r["attempts"] for r in refused if r["has_sound_proposal"])
        rows.append({"system": name, "refusals": len(refused), "solved_at_attempt_1": solved.get(1, 0),
                     "solved_at_attempt_2": solved.get(2, 0), "solved_at_attempt_3": solved.get(3, 0),
                     "no_way_to_approval": sum(not r["has_sound_proposal"] for r in refused)})
    return rows


def llm_tables(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Guard and fallback statistics of the full system, read from the trail of each file."""
    per_agent: dict[str, Counter] = defaultdict(Counter)
    files = []
    for r in rows:
        totals = trace.summarise(r["_trail"])
        files.append({"applicant_id": r["applicant_id"], "steps": totals["steps"], "llm_steps": totals["llm_steps"],
                      "fallback_steps": totals["fallback_steps"], "llm_calls": totals["llm_calls"],
                      "prompt_tokens": totals["prompt_tokens"], "completion_tokens": totals["completion_tokens"],
                      "answers": totals["answers"], "rejected_structure": totals["rejected_structure"],
                      "rejected_check": totals["rejected_check"], "rejected_numbers": totals["rejected_numbers"],
                      "no_answer": totals["no_answer"], "ms": r["ms"]})
        for step in r["_trail"]:
            c = per_agent[step["agent"]]
            c["steps"] += 1
            c["llm_asked"] += bool(step.get("llm_asked"))
            c["llm_steps"] += step["mode"] == "llm"
            c["fallback"] += bool(step.get("llm_asked")) and step["mode"] == "rules"
            c["calls"] += step["llm"]["calls"]
            c["tokens"] += step["llm"]["prompt_tokens"] + step["llm"]["completion_tokens"]
            c["ms"] += step["duration_ms"]
            for g in step.get("guards", []):
                c["answers"] += 1
                c[g["guard"]] += 1
    agents = []
    for agent, c in per_agent.items():
        answers, asked = max(c["answers"], 1), max(c["llm_asked"], 1)
        agents.append({
            "agent": agent, "steps": c["steps"], "steps_asking_the_llm": c["llm_asked"],
            "steps_written_by_the_llm": c["llm_steps"], "fallback_to_rules": round(c["fallback"] / asked, 4),
            "answers": c["answers"], "accepted": round(c["accepted"] / answers, 4),
            "rejected_structure": round(c["structure"] / answers, 4), "rejected_check": round(c["check"] / answers, 4),
            "rejected_numbers": round(c["numbers"] / answers, 4), "no_answer": round(c["no_answer"] / answers, 4),
            "llm_calls": c["calls"], "tokens_per_step": round(c["tokens"] / max(c["steps"], 1), 1),
            "ms_per_step": round(c["ms"] / max(c["steps"], 1), 1)})
    return agents, files


# --------------------------------------------------------------------------- output
def write_csv(name: str, rows: list[dict]) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / name
    columns: list[str] = []
    for r in rows:
        columns += [k for k in r if k not in columns and not k.startswith("_")]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _md(rows: list[dict], columns: list[tuple[str, str]], percent: tuple[str, ...] = ()) -> str:
    def cell(r: dict, key: str) -> str:
        v = r.get(key)
        if v is None:
            return "n/a"
        if key in percent:
            return f"{v * 100:.0f}%"
        if isinstance(v, float):
            return f"{v:.0f}" if abs(v) >= 10 else f"{v:.2f}"
        return str(v)

    head = "| " + " | ".join(title for _, title in columns) + " |\n|" + "---|" * len(columns)
    return head + "\n" + "\n".join("| " + " | ".join(cell(r, k) for k, _ in columns) + " |" for r in rows)


def write_markdown(meta: dict, systems: list[dict], generators: list[dict], attempts: list[dict],
                   agents: list[dict] | None, not_run: list[str]) -> Path:
    comparison = group_fairness_comparison()
    fair = []
    for attribute in comparison["full"]["attributes"]:
        a, b = comparison["full"]["attributes"][attribute], comparison["unaware"]["attributes"][attribute]
        fair.append({"attribute": a["label"], "dp_full": a["demographic_parity_difference"],
                     "eo_full": a["equalized_odds_difference"], "ratio_full": a["demographic_parity_ratio"],
                     "dp_unaware": b["demographic_parity_difference"], "eo_unaware": b["equalized_odds_difference"],
                     "ratio_unaware": b["demographic_parity_ratio"],
                     "note": "too few files in one group" if a["reliable_gap"] is None else
                             "above tolerance" if a["alert"] else ""})
    pct = ("valid", "actionable", "robust", "plausible", "sound", "refusals_with_sound_way",
           "refusals_given_unsound_proposal", "decision_agreement")
    lines = [
        "# Evaluation results", "",
        f"Generated by `python eval/run_eval.py` on {meta['date']}.", "",
        f"- Files: {meta['files']} held-out test files ({meta['refused']} refused by the model)",
        f"- Model: `{meta['model']}`, refusal threshold {meta['threshold']:.2f}",
        f"- Agents: {meta['agents']}", "",
        "Every proposal delivered by a system is judged again by the same tools: it is **sound** when the decision "
        "flips after re-scoring, the recourse rules are respected, the threshold is cleared with a safety margin and "
        "the modified file stays close to real past applicants.", "",
        "How to read it: these four checks are the ones the Vérificateur-Équité applies, so the full system and the "
        "no_loop ablation deliver 100% sound proposals by construction. The informative figures are how many refusals "
        "still leave with a sound way (coverage), and what the systems without the auditor hand to applicants.", "",
        "## 1. Full system, ablations and baselines", "",
        _md(systems, [("system", "System"), ("refusals", "Refusals"), ("proposals_delivered", "Proposals delivered"),
                      ("sound", "of which sound"), ("refusals_with_sound_way", "Refusals with a sound way"),
                      ("refusals_given_unsound_proposal", "Refusals handed an unsound proposal"),
                      ("sensitive_dependence_caught", "Sensitive dependence caught"),
                      ("escalated_to_human", "Sent to a human"), ("ms_per_file", "ms per file")], pct), "",
        f"Files whose decision changes with a protected attribute: {systems[0]['sensitive_dependent_files']}. "
        "A system that catches none of them closes these files without anyone looking.", "",
        "Why a delivered proposal is unsound:", "",
        _md(systems, [("system", "System"), ("valid", "Valid"), ("actionable", "Actionable"), ("robust", "Robust"),
                      ("plausible", "Plausible"), ("sound", "Sound"), ("mean_sparsity", "Changes per proposal"),
                      ("mean_proximity", "Proximity (Gower)"), ("mean_plausibility", "Plausibility score")], pct), "",
        "## 2. What the rejection loop brings", "",
        _md(attempts, [("system", "System"), ("refusals", "Refusals"), ("solved_at_attempt_1", "Solved at attempt 1"),
                       ("solved_at_attempt_2", "Attempt 2"), ("solved_at_attempt_3", "Attempt 3"),
                       ("no_way_to_approval", "No way to approval")]), "",
        "## 3. Counterfactual generators", "",
        "Up to three changes, standard ranges, on the refused files. The exhaustive search only returns combinations "
        "that it scored as valid and that respect the rules by construction; DiCE samples freely and is filtered afterwards.", "",
        _md(generators, [("generator", "Generator"), ("candidates", "Candidates"), ("validity", "Validity"),
                         ("actionability_rate", "Actionability rate"), ("robust", "Robust"), ("plausible", "Plausible"),
                         ("sound", "Sound"), ("proximity", "Proximity"), ("sparsity", "Sparsity"),
                         ("plausibility", "Plausibility"), ("coverage_sound", "Refusals covered"),
                         ("ms_per_file", "ms per file")],
            ("validity", "actionability_rate", "robust", "plausible", "sound", "coverage_sound")), "",
        "Proximity: mean Gower distance to the original file (lower is closer). Sparsity: number of attributes changed. "
        "Plausibility: share of real past files at least as isolated as the modified file (higher is more realistic).", "",
        "## 4. Group fairness (Fairlearn)", "",
        _md(fair, [("attribute", "Attribute"), ("dp_full", "DP difference, audited model"), ("eo_full", "EO difference"),
                   ("ratio_full", "DP ratio"), ("dp_unaware", "DP difference, without protected attributes"),
                   ("eo_unaware", "EO difference"), ("ratio_unaware", "DP ratio"), ("note", "Note")]), "",
        *[f"- {line}" for line in comparison["reading"]], "",
    ]
    if agents:
        lines += ["## 5. Language model runs", "",
                  _md(agents, [("agent", "Agent"), ("steps", "Steps"), ("steps_written_by_the_llm", "Written by the LLM"),
                               ("fallback_to_rules", "Fallback to rules"), ("answers", "Answers"), ("accepted", "Accepted"),
                               ("rejected_structure", "Rejected: structure"), ("rejected_check", "Rejected: agent check"),
                               ("rejected_numbers", "Rejected: invented number"), ("no_answer", "No answer"),
                               ("tokens_per_step", "Tokens per step"), ("ms_per_step", "ms per step")],
                      ("fallback_to_rules", "accepted", "rejected_structure", "rejected_check", "rejected_numbers", "no_answer")), ""]
    if not_run:
        lines += ["## Not run", "", *[f"- {line}" for line in not_run], ""]
    path = RESULTS / "RESULTS.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def load_files(limit: int | None) -> list[tuple[LoanApplication, int]]:
    test = pd.read_csv(ROOT / "ml" / "data" / "processed" / "test.csv")
    if limit:
        test = test.head(limit)
    return [(LoanApplication(**{k: v for k, v in rec.items() if k != "default"}), int(rec["default"]))
            for rec in test.to_dict("records")]


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=None, help="only the first N test files")
    parser.add_argument("--llm", action="store_true", help="also run what needs a language model (provider in backend/.env)")
    parser.add_argument("--llm-files", type=int, default=30, help="files sent through the language model (default 30)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    say = (lambda *a: None) if args.quiet else print

    files = load_files(args.limit)
    use_llm = args.llm and llm.enabled()
    provider, model_name = config.LLM_PROVIDER, llm.describe()["model"]
    not_run: list[str] = []
    if args.llm and not llm.enabled():
        not_run.append("--llm was asked but LLM_PROVIDER is `none`: set a provider and a key in backend/.env.")

    # Tables 1 to 4 are measured with the agents on rules, so they are exact and reproducible.
    config.LLM_PROVIDER = "none"
    plans: dict[str, Callable] = {
        "full": run_graph(graph), "no_loop": run_graph(build_graph(verification_loop=False)),
        "no_verifier": run_no_verifier, "single_pass": run_single_pass,
    }
    per_system: dict[str, list[dict]] = {}
    for name, run in plans.items():
        started = time.perf_counter()
        per_system[name] = [run(app, y) for app, y in files]
        say(f"{name:14s} {len(files)} files in {time.perf_counter() - started:5.1f} s")
    systems = [system_table(name, rows) for name, rows in per_system.items()]

    agents_rows = files_rows = None
    if use_llm:
        config.LLM_PROVIDER = provider
        subset = files[:args.llm_files]
        started = time.perf_counter()
        llm_rows = [run_graph(graph)(app, y) for app, y in subset]
        say(f"{'full + llm':14s} {len(subset)} files in {time.perf_counter() - started:5.1f} s")
        agents_rows, files_rows = llm_tables(llm_rows)
        per_system["full_llm"] = llm_rows
        answered, unusable = [], 0
        started = time.perf_counter()
        for app, y in subset:
            row = run_single_prompt(app, y)
            if row is None:
                unusable += 1
            else:
                answered.append(row)
        say(f"{'single_prompt':14s} {len(subset)} files in {time.perf_counter() - started:5.1f} s")
        per_system["single_prompt"] = answered
        systems.append(system_table("single_prompt", answered, unusable))
        config.LLM_PROVIDER = "none"
    else:
        not_run.append("single_prompt baseline and language model statistics: they need a provider. "
                       "Run `python eval/run_eval.py --llm` with LLM_PROVIDER and LLM_API_KEY set in backend/.env.")

    generators = generator_table(files)
    attempts = attempts_table(per_system)
    written = [write_csv("systems.csv", systems), write_csv("counterfactuals.csv", generators),
               write_csv("fairness.csv", fairness_table()), write_csv("attempts.csv", attempts)]
    for name, rows in per_system.items():
        written.append(write_csv(f"per_file_{name}.csv", rows))
    if agents_rows:
        written += [write_csv("llm_agents.csv", agents_rows), write_csv("llm_files.csv", files_rows)]
    meta = {"date": f"{datetime.now(timezone.utc):%d %B %Y, %H:%M} UTC", "files": len(files),
            "refused": sum(r["model_decision"] == "refused" for r in per_system["full"]),
            "model": scoring.model().version, "threshold": scoring.threshold(),
            "agents": ("rules for tables 1 to 4" + (f"; {provider} ({model_name}) on {args.llm_files} files for table 5 "
                                                    "and the single_prompt baseline" if use_llm else ""))}
    written.append(write_markdown(meta, systems, generators, attempts, agents_rows, not_run))
    config.LLM_PROVIDER = provider
    say("\nWritten:")
    for path in written:
        say("  ", path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    if not args.quiet:
        print()
        print(_md(systems, [("system", "System"), ("proposals_delivered", "Proposals"), ("sound", "Sound"),
                            ("refusals_with_sound_way", "Refusals with a sound way"),
                            ("refusals_given_unsound_proposal", "Handed an unsound proposal"),
                            ("sensitive_dependence_caught", "Sensitive caught"), ("ms_per_file", "ms/file")],
                  ("sound", "refusals_with_sound_way", "refusals_given_unsound_proposal")))
    return {"systems": systems, "generators": generators, "attempts": attempts, "agents": agents_rows,
            "per_system": per_system, "files": written}


if __name__ == "__main__":
    main()
