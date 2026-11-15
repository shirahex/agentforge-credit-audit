import math

import pytest

from app.samples import sample
from app.tools import scoring
from app.tools.analysis import similar_cases, validate_application
from app.tools.counterfactuals import (check_actionability, dice_search, exhaustive_search,
                                       generate_counterfactuals, permitted_moves)


def test_shap_contributions_add_up_to_the_calibrated_score():
    app = sample("terms")
    m = scoring.model()
    contrib, base = m.contributions(app.features())
    p = scoring.score_applicant(app).default_probability
    assert 1 / (1 + math.exp(-(sum(contrib.values()) + base))) == pytest.approx(p, abs=1e-4)


def test_risk_never_decreases_with_duration_or_amount():
    app = sample("second_attempt").features()
    for feature, values in (("duration_months", range(6, 73, 6)), ("credit_amount", range(500, 15001, 500))):
        probs = scoring.probabilities({**app, feature: v} for v in values)
        assert all(b >= a - 1e-9 for a, b in zip(probs, probs[1:])), feature


def test_score_matches_decision_rule():
    for tag in ("terms", "approved"):
        s = scoring.score_applicant(sample(tag))
        assert (s.default_probability >= s.threshold) == (s.decision == "refused")
        assert len(s.top_factors) == 6 and s.model_version


def test_actionability_rules():
    app = sample("terms")
    assert check_actionability(app, {"age": app.age + 10})[0] is False
    assert check_actionability(app, {"sex": "male"})[0] is False
    assert check_actionability(app, {"purpose": "education"})[0] is False
    assert check_actionability(app, {"credit_amount": app.credit_amount + 500})[0] is False
    assert check_actionability(app, {"credit_amount": int(app.credit_amount * 0.3)})[0] is False
    assert check_actionability(app, {"credit_amount": int(app.credit_amount * 0.8)})[0] is True
    assert check_actionability(app, {"other_debtors": "guarantor"})[0] is True


def test_permitted_moves_only_improve():
    app = sample("second_attempt")
    for name, values in permitted_moves(app, widen=True).items():
        for v in values:
            assert check_actionability(app, {name: v})[0], (name, v)


def test_exhaustive_counterfactuals_really_flip_the_decision():
    app = sample("terms")
    found = exhaustive_search(app, max_changes=2)
    assert found
    for cf in found:
        changed = {c.feature: c.to_value for c in cf.changes}
        p = float(scoring.probabilities([{**app.features(), **changed}])[0])
        assert p == pytest.approx(cf.new_probability, abs=1e-4)
        assert cf.valid and p < scoring.threshold() and cf.actionable and cf.statement


def test_dice_candidates_are_rescored_and_checked():
    app = sample("second_attempt")
    for cf in dice_search(app):
        changed = {c.feature: c.to_value for c in cf.changes}
        p = float(scoring.probabilities([{**app.features(), **changed}])[0])
        assert cf.valid == (p < scoring.threshold())
        assert cf.actionable == check_actionability(app, changed)[0]


def test_generated_set_is_ranked_and_varied():
    cfs = [c for c in generate_counterfactuals(sample("second_attempt"), max_changes=3) if c.valid and c.actionable]
    assert len(cfs) >= 2
    sets = [frozenset(ch.feature for ch in c.changes) for c in cfs]
    assert len(sets) == len(set(sets))


def test_file_analysis():
    app = sample("approved")
    rate, peers = similar_cases(app)
    assert 0 <= rate <= 1 and len(peers) == 5 and peers[0].distance <= peers[-1].distance
    odd = app.model_copy(update={"employment": "ge_7y", "age": 20, "credit_amount": 19000, "duration_months": 6})
    assert len(validate_application(odd)) >= 2
