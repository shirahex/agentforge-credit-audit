"""Fairness and plausibility tools (task I1)."""
import numpy as np
import pytest

from app import config
from app.samples import sample
from app.tools import fairness, scoring
from app.tools.counterfactuals import exhaustive_search
from app.tools.fairness import (fairness_from_predictions, group_context, group_fairness_comparison,
                                group_fairness_metrics, group_fairness_report, plausibility_score,
                                sensitive_flip_test)


def test_constructed_unfair_decisions_are_measured_exactly():
    """Every man approved, every woman refused, whatever they repaid: the worst possible case."""
    groups = ["male"] * 50 + ["female"] * 50
    y_true = [1, 0] * 50
    y_pred = [1] * 50 + [0] * 50
    r = fairness_from_predictions(y_true, y_pred, groups)
    assert r["demographic_parity_difference"] == 1.0
    assert r["demographic_parity_ratio"] == 0.0
    assert r["equalized_odds_difference"] == 1.0
    assert r["least_approved"] == "female" and r["most_approved"] == "male"
    assert r["groups"]["female"]["selection_rate"] == 0.0 and r["groups"]["male"]["n"] == 50


def test_fair_decisions_score_zero():
    """Same approval rate and same error rates in both groups."""
    groups = ["a"] * 40 + ["b"] * 40
    y_true = [1, 1, 0, 0] * 20
    y_pred = [1, 0, 1, 0] * 20
    r = fairness_from_predictions(y_true, y_pred, groups)
    assert r["demographic_parity_difference"] == 0 and r["equalized_odds_difference"] == 0
    assert r["demographic_parity_ratio"] == 1


def test_equal_approval_rates_can_hide_unequal_errors():
    """Demographic parity holds, yet group b's good payers are the ones refused."""
    groups = ["a"] * 4 + ["b"] * 4
    y_true = [1, 1, 0, 0, 1, 1, 0, 0]
    y_pred = [1, 1, 0, 0, 0, 0, 1, 1]
    r = fairness_from_predictions(y_true, y_pred, groups)
    assert r["demographic_parity_difference"] == 0
    assert r["equalized_odds_difference"] == 1.0


def test_an_unfair_model_is_caught_on_the_test_set(monkeypatch):
    """A model that refuses every woman must come out of the tool as a maximal disparity."""
    class RefusesWomen:
        version, variant, threshold = "unfair-test", "full", 0.5

        def predict_default(self, rows):
            return np.array([0.9 if r["sex"] == "female" else 0.1 for r in rows])

    monkeypatch.setattr(fairness, "get_model", lambda variant="full": RefusesWomen())
    fairness._group_report.cache_clear()
    try:
        sex = fairness._group_report("full", 0.5, 0)["attributes"]["sex"]
    finally:
        fairness._group_report.cache_clear()
    assert sex["demographic_parity_difference"] == 1.0 and sex["equalized_odds_difference"] == 1.0
    assert sex["alert"] and not sex["four_fifths_ok"] and sex["least_approved"] == "female"


def test_group_report_matches_a_direct_count():
    report = group_fairness_report("full")
    test = fairness._test_set()
    probs = scoring.model().predict_default(test.drop(columns=["default", "applicant_id"]).to_dict("records"))
    approved = probs < report["threshold"]
    for sex in ("male", "female"):
        mask = (test["sex"] == sex).to_numpy()
        got = report["attributes"]["sex"]["groups"][sex]
        assert got["n"] == mask.sum() and got["selection_rate"] == pytest.approx(approved[mask].mean(), abs=1e-4)
    sex = report["attributes"]["sex"]
    rates = [g["selection_rate"] for g in sex["groups"].values()]
    assert sex["demographic_parity_difference"] == pytest.approx(max(rates) - min(rates), abs=1e-4)
    low, high = sex["ci95"]["demographic_parity_difference"]
    assert 0 <= low <= high <= 1


def test_metrics_cover_sex_and_age_for_both_variants():
    flat = group_fairness_metrics()
    for attribute in ("sex", "age_group"):
        assert {f"dp_diff_{attribute}", f"dp_ratio_{attribute}", f"eo_diff_{attribute}"} <= set(flat)
        assert 0 <= flat[f"dp_diff_{attribute}"] <= 1
    assert all(isinstance(v, float) for v in flat.values())
    both = group_fairness_comparison()
    assert both["full"]["variant"] == "full" and both["unaware"]["variant"] == "unaware"
    assert len(both["reading"]) == 3
    # Removing sex from the model removes most of the gap between men and women.
    gap = lambda v: both[v]["attributes"]["sex"]["demographic_parity_difference"]  # noqa: E731
    assert gap("unaware") < gap("full")


def test_small_groups_never_raise_an_alert():
    foreign = group_fairness_report("full")["attributes"]["foreign_worker"]
    small = [g for g, v in foreign["groups"].items() if v["n"] < config.FAIRNESS_MIN_GROUP]
    assert small and all(foreign["groups"][g]["small_sample"] for g in small)
    assert foreign["alert"] is False


def test_group_context_places_the_applicant():
    app = sample("no_path")
    by_attr = {c["attribute"]: c for c in group_context(app)}
    assert by_attr["sex"]["group"] == app.sex
    assert by_attr["age_group"]["group"] == fairness.age_band(app.age)
    assert by_attr["age_group"]["gap"] >= 0


def test_flip_test_reports_one_delta_per_sensitive_attribute():
    ok, metrics = sensitive_flip_test(sample("approved"))
    assert ok and set(metrics) == {"flip_delta_sex", "flip_delta_foreign_worker"}
    assert sensitive_flip_test(sample("sensitive"))[0] is False


def test_plausibility_of_an_untouched_file_and_of_an_absurd_one():
    app = sample("terms")
    same = plausibility_score(app, {})
    assert same.plausible and same.knn_distance == same.applicant_distance and 0 <= same.score <= 1
    absurd = plausibility_score(app, {
        "credit_amount": 20000, "duration_months": 4, "installment_rate": 1, "existing_credits": 4,
        "purpose": "retraining", "job": "unskilled_non_resident", "employment": "unemployed",
        "property": "none", "housing": "free", "credit_history": "no_credits", "residence_since": 1})
    assert not absurd.plausible and absurd.knn_distance > absurd.limit and absurd.score < 0.05
    assert absurd.score < same.score


def test_plausibility_grows_with_the_size_of_the_change():
    app = sample("second_attempt")
    small = plausibility_score(app, {"duration_months": app.duration_months - 6})
    large = plausibility_score(app, {"duration_months": 4, "credit_amount": 250, "savings": "ge_1000",
                                     "checking_status": "high", "other_debtors": "guarantor"})
    assert small.knn_distance < large.knn_distance


def test_plausibility_accepts_a_counterfactual_object():
    app = sample("terms")
    cf = exhaustive_search(app, max_changes=2)[0]
    by_object = plausibility_score(app, cf)
    by_dict = plausibility_score(app, {c.feature: c.to_value for c in cf.changes})
    assert by_object == by_dict and 0 <= by_object.neighbours_repaid <= 1
