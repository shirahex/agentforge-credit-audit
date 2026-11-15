"""Each demo file must follow the path of the graph it was chosen for."""
from app.graph.build import graph
from app.samples import sample


def audit(tag: str):
    out = graph.invoke({"application": sample(tag)})
    return out, out["decision"]


def test_refusal_solved_by_loan_terms_on_first_attempt():
    out, d = audit("terms")
    assert d.decision == "refused" and d.attempts == 1 and not d.escalated
    assert d.counterfactuals and all(c.valid and c.actionable and c.robust for c in d.counterfactuals)
    assert all(c.effort == "immediate" for c in d.counterfactuals)


def test_second_attempt_widens_the_search_after_a_rejection():
    out, d = audit("second_attempt")
    assert d.decision == "refused" and d.attempts == 2 and not d.escalated
    assert len(set(out["cf_plans"])) == 2, "a failed plan must not be replayed"
    assert any(c.effort == "medium_term" for c in d.counterfactuals)


def test_approval_skips_counterfactuals():
    _, d = audit("approved")
    assert d.decision == "approved" and d.attempts == 0 and d.counterfactuals == [] and not d.escalated


def test_borderline_score_is_escalated():
    _, d = audit("borderline")
    assert d.escalated and "borderline" in d.escalation_reason


def test_sensitive_attribute_dependence_is_escalated():
    out, d = audit("sensitive")
    assert not out["fairness"].flip_test_passed
    assert d.escalated and "sensitive" in d.escalation_reason


def test_no_path_stops_after_three_attempts():
    out, d = audit("no_path")
    assert d.attempts == 3 and d.counterfactuals == [] and d.escalated
    assert len(set(out["cf_plans"])) == 3
