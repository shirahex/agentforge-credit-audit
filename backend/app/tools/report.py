"""Audit report rendering. Owner: Imane (task I5).

TODO: render the AuditDecision and the event trail into a PDF and return
its path. The function signature is used by the Arbitre agent.
"""
from __future__ import annotations

from app.schemas import AuditDecision


def render_report(decision: AuditDecision, events: list[dict]) -> str | None:
    return None
