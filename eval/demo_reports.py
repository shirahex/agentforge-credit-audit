"""Generates the PDF audit report of each of the six demo files (task I5).

    python eval/demo_reports.py

Each file goes through the durable graph, exactly as from the interface. The
escalated ones are reviewed so that the reports show a human decision: the
`sensitive` file is approved by the reviewer (the model is overturned), the
`borderline` and `no_path` files are confirmed. Reports are written to
docs/sample-reports/<tag>.pdf, together with the interim report of the
`sensitive` file as it stands while the run waits for its reviewer.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="agentforge-demo-")
os.environ["STEP_DELAY_SECONDS"] = "0"

from app.graph.runner import AuditService  # noqa: E402
from app.memory import run_store  # noqa: E402
from app.samples import load_samples, sample  # noqa: E402

OUT = ROOT / "docs" / "sample-reports"
REVIEWS = {
    "borderline": {"outcome": "approved", "reviewer": "I. Alouani",
                   "comment": "Score on the threshold. The file is consistent and raises no warning."},
    "sensitive": {"outcome": "approved", "reviewer": "I. Alouani",
                  "comment": "Foreign-worker status must not decide. One verified way to approval exists and the file is consistent."},
    "no_path": {"outcome": "refused", "reviewer": "M. Daouki",
                "comment": "No realistic change brings the file under the threshold. Refusal confirmed."},
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    service = AuditService()
    for s in load_samples():
        tag = s["tag"]
        run_id = service.start(sample(tag), background=False)
        decision = run_store.get(run_id)["decision"]
        if decision["escalated"]:
            if tag == "sensitive":
                shutil.copy(decision["report_path"], OUT / f"{tag}-waiting-for-review.pdf")
            service.review(run_id, REVIEWS[tag])
            decision = run_store.get(run_id)["decision"]
        shutil.copy(decision["report_path"], OUT / f"{tag}.pdf")
        print(f"{tag:15s} {decision['decision']:9s} final {decision['final_outcome']:9s} "
              f"{decision['report_id']}  ->  docs/sample-reports/{tag}.pdf")


if __name__ == "__main__":
    main()
