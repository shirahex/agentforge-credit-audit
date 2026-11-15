from app.graph.build import graph
from app.samples import APPROVED, BORDERLINE, REFUSED


def test_refused_file_goes_through_the_verifier_loop():
    out = graph.invoke({"application": REFUSED})
    d = out["decision"]
    assert d.decision == "refused"
    # First attempt touches an immutable feature and is rejected, second succeeds.
    assert d.attempts == 2
    assert d.counterfactuals and all(c.valid and c.actionable for c in d.counterfactuals)
    assert not d.escalated


def test_approved_file_skips_counterfactuals():
    d = graph.invoke({"application": APPROVED})["decision"]
    assert d.decision == "approved"
    assert d.attempts == 0 and d.counterfactuals == []


def test_borderline_file_is_escalated():
    d = graph.invoke({"application": BORDERLINE})["decision"]
    assert d.escalated and "borderline" in d.escalation_reason
