"""Demo applicant files: real test-set applicants chosen by ml/select_samples.py
so that each one exercises a different path of the agent graph."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.schemas import LoanApplication

_FILE = Path(__file__).with_name("samples.json")


@lru_cache(maxsize=1)
def load_samples() -> list[dict]:
    return json.loads(_FILE.read_text(encoding="utf-8")) if _FILE.exists() else []


def sample(tag: str) -> LoanApplication:
    for s in load_samples():
        if s["tag"] == tag:
            return LoanApplication(**s["application"])
    raise KeyError(tag)
