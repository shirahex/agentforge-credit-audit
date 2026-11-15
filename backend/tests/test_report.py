"""PDF audit report (task I5)."""
import re
import subprocess
import shutil

import pytest
from pypdf import PdfReader

from app import config
from app.graph.runner import AuditService
from app.memory import run_store
from app.samples import load_samples, sample
from app.schemas import AuditDecision
from app.tools.report import fingerprint, render_report

config.STEP_DELAY_SECONDS = 0
TAGS = [s["tag"] for s in load_samples()]


def pages(path: str) -> list[str]:
    return [re.sub(r"\s+", " ", p.extract_text()) for p in PdfReader(path).pages]


@pytest.fixture(scope="module")
def service():
    return AuditService()


@pytest.mark.parametrize("tag", TAGS)
def test_a_report_is_generated_for_each_demo_file(service, tag):
    run_id = service.start(sample(tag), background=False)
    d = run_store.get(run_id)["decision"]
    assert d["report_id"].startswith("AF-") and d["report_path"].endswith(f"{d['report_id']}.pdf")
    text = pages(d["report_path"])
    whole = " ".join(text)
    for section in ("1. Decision", "2. Applicant file", "3. Main factors", "4. Verified ways to approval",
                    "6. Fairness", "7. Human decision", "8. Agent trail", "9. Applicant letter", "10. Integrity"):
        assert section in whole, section
    assert ("5. Attempts and rejected proposals" in whole) == (d["decision"] == "refused")
    # identifier, date and model version on every page
    model_version = run_store.events(run_id)[1]["payload"]["score"]["model_version"]
    for i, page in enumerate(text, 1):
        assert d["report_id"] in page and model_version in page and "Generated" in page
        assert f"Page {i} of {len(text)}" in page
    assert sample(tag).applicant_id in whole
    assert "Approval gap" in whole and "sensitive_flip_test" in whole and "Objet : votre demande de crédit" in whole


def test_report_shows_rejected_attempts_and_the_objections(service):
    run_id = service.start(sample("second_attempt"), background=False)
    whole = " ".join(pages(run_store.get(run_id)["decision"]["report_path"]))
    assert "Attempt 1 rejected by the auditor" in whole and "Attempt 2 accepted by the auditor" in whole
    assert "Next plan: loan terms alone are not enough" in whole


def test_interim_report_then_final_report_with_the_human_decision(service):
    run_id = service.start(sample("sensitive"), background=False)
    interim = " ".join(pages(run_store.get(run_id)["decision"]["report_path"]))
    assert "INTERIM REPORT: WAITING FOR HUMAN REVIEW" in interim and "Waiting for a reviewer" in interim
    assert "Draft, not to be sent" in interim
    service.review(run_id, {"outcome": "approved", "reviewer": "I. Alouani", "comment": "Nationality must not decide."})
    final = " ".join(pages(run_store.get(run_id)["decision"]["report_path"]))
    assert "INTERIM REPORT" not in final and "Approved after human review" in final
    assert "I. Alouani" in final and "Nationality must not decide." in final and "overturning" in final
    assert "Final version, in French" in final


def test_fingerprint_is_stable_and_detects_a_change(service):
    run_id = service.start(sample("terms"), background=False)
    run = run_store.get(run_id)
    decision = AuditDecision(**run["decision"])
    from app.graph import trace

    steps = trace.read(run_id)
    app = run["application"]
    app.pop("applicant_id")
    a = fingerprint(app, decision, steps)
    assert a == fingerprint(app, decision, steps) and len(a) == 64
    assert a in " ".join(pages(decision.report_path)).replace(" ", "")
    tampered = decision.model_copy(update={"default_probability": 0.01})
    assert fingerprint(app, tampered, steps) != a
    assert fingerprint({**app, "credit_amount": 1}, decision, steps) != a


def test_report_without_a_score_is_not_written():
    d = AuditDecision(applicant_id="X", decision="approved", default_probability=0.1)
    assert render_report(d, []) is None


@pytest.mark.skipif(shutil.which("pdffonts") is None, reason="poppler not installed")
def test_report_uses_only_standard_fonts(service):
    run_id = service.start(sample("approved"), background=False)
    out = subprocess.run(["pdffonts", run_store.get(run_id)["decision"]["report_path"]], capture_output=True, text=True)
    assert "Helvetica" in out.stdout
