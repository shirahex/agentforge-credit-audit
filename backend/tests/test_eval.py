"""Evaluation harness (task I6): one command produces the result tables."""
import csv
import importlib.util
from pathlib import Path

import pytest

from app import config
from app.llm import client
from app.samples import sample
from app.tools import scoring

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def harness():
    spec = importlib.util.spec_from_file_location("run_eval", ROOT / "eval" / "run_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_one_command_writes_every_table(harness, tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RESULTS", tmp_path)
    out = harness.main(["--limit", "24", "--quiet"])
    names = {p.name for p in tmp_path.iterdir()}
    assert {"systems.csv", "counterfactuals.csv", "fairness.csv", "attempts.csv", "RESULTS.md", "per_file_full.csv",
            "per_file_no_loop.csv", "per_file_no_verifier.csv", "per_file_single_pass.csv"} <= names

    systems = {r["system"]: r for r in read(tmp_path / "systems.csv")}
    assert set(systems) == {"full", "no_loop", "no_verifier", "single_pass"}
    assert all(int(r["files"]) == 24 for r in systems.values())
    # The auditor lets nothing unsound through; the loop never loses a file the single attempt solved.
    assert float(systems["full"]["sound"]) == 1.0 and float(systems["full"]["refusals_given_unsound_proposal"]) == 0
    assert float(systems["full"]["refusals_with_sound_way"]) >= float(systems["no_loop"]["refusals_with_sound_way"])
    assert int(systems["no_verifier"]["sensitive_dependence_caught"]) == 0
    assert int(systems["full"]["sensitive_dependence_caught"]) == int(systems["full"]["sensitive_dependent_files"])

    generators = {r["generator"]: r for r in read(tmp_path / "counterfactuals.csv")}
    assert set(generators) == {"exhaustive", "dice"}
    for column in ("validity", "proximity", "sparsity", "plausibility", "actionability_rate"):
        assert generators["exhaustive"][column] != ""
    assert float(generators["exhaustive"]["actionability_rate"]) == 1.0

    fairness = read(tmp_path / "fairness.csv")
    assert {r["model"] for r in fairness} == {"full", "unaware"}
    assert any(r["row"] == "difference" and r["attribute"] == "sex" for r in fairness)
    text = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    assert "## 1. Full system, ablations and baselines" in text and "## Not run" in text
    assert out["agents"] is None


def test_assess_judges_a_proposal_with_the_tools(harness):
    app = sample("terms")
    good = harness.assess(app, {"duration_months": 8})
    assert good["well_formed"] and good["valid"] and good["actionable"] and good["sparsity"] == 1
    assert good["new_probability"] < scoring.threshold() and 0 < good["proximity"] < 0.1
    protected = harness.assess(app, {"sex": "female"})
    assert not protected["actionable"] and not protected["sound"]
    nonsense = harness.assess(app, {"salary": 9000})
    assert not nonsense["well_formed"] and not nonsense["sound"]
    out_of_range = harness.assess(app, {"credit_amount": 5})
    assert not out_of_range["well_formed"]


def test_single_prompt_baseline_is_scored_against_the_model(harness, monkeypatch):
    app = sample("terms")
    answer = {"decision": "approved", "default_probability": 0.9, "factors": ["checking_status", "shoe_size", "duration_months"],
              "proposals": [{"age": 60}]}
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(client, "ask_json", lambda system, user, **_: answer)
    row = harness.run_single_prompt(app, 0)
    assert row["decision"] == "approved" and row["model_decision"] == "refused" and not row["decision_agrees"]
    assert row["probability_error"] == pytest.approx(0.9 - row["model_probability"], abs=1e-3)
    assert row["proposals"] == 0, "an approval comes with no proposal"
    assert 0 <= row["factors_in_shap_top6"] < 1

    answer.update(decision="refused", proposals=[{"age": 60}, {"duration_months": 8}, "nonsense"])
    row = harness.run_single_prompt(app, 0)
    assert row["proposals"] == 2 and row["proposals_actionable"] == 1 and row["proposals_valid"] >= 1
    monkeypatch.setattr(client, "ask_json", lambda system, user, **_: {"text": "I cannot decide"})
    assert harness.run_single_prompt(app, 0) is None


def test_llm_tables_count_guards_and_fallbacks(harness, monkeypatch):
    bad = {"explanation": "The applicant has a 93% chance of default because of a salary of 1200 DM.",
           "cited_features": ["checking_status"]}
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(client, "ask_json", lambda system, user, **_: bad if "scoring analyst" in system else None)
    rows = [harness.run_graph(harness.graph)(sample("approved"), 0)]
    agents, files = harness.llm_tables(rows)
    by_agent = {a["agent"]: a for a in agents}
    assert by_agent["Modèle-Scoring"]["rejected_numbers"] == 1.0 and by_agent["Modèle-Scoring"]["fallback_to_rules"] == 1.0
    assert by_agent["Analyste-Dossier"]["no_answer"] == 1.0
    assert files[0]["rejected_numbers"] == 2 and files[0]["fallback_steps"] == files[0]["llm_steps"]
