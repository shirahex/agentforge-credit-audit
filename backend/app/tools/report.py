"""PDF audit report (task I5).

`render_report` turns one audit into the document an auditor reads:

    1. Decision                 outcome, default risk against the threshold, summary
    2. Applicant file           the 20 attributes, protected ones marked
    3. Main factors             exact SHAP contributions
    4. Ways to approval         verified proposals, with risk after and plausibility
    5. Attempts                 every plan, what the auditor rejected and why
    6. Fairness                 flip test of this file, Fairlearn group metrics of the model
    7. Human decision           reviewer, outcome and reason, or "waiting for review"
    8. Agent trail              every step with its tool calls, results and durations
    9. Applicant letter         the French letter, marked as a draft until the audit is closed
   10. Integrity and limits     SHA-256 fingerprint of the audited content, scope of the report

The report identifier, the generation date and the model version are printed
on every page, with the page number.

Everything is drawn with ReportLab (text, tables and vector shapes): no
image file, no chart library, no network access. Colours follow the design
tokens of the interface: green, red and amber only mean approved, refused
and human review.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (Flowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from app import config
from app.domain.features import BY_NAME, FEATURES
from app.memory.db import data_dir
from app.schemas import AuditDecision, LoanApplication

INK, SOFT, MUTED, FAINT = (colors.HexColor(c) for c in ("#1d1d1f", "#424245", "#6e6e73", "#a1a1a6"))
HAIRLINE, CANVAS, ACCENT = (colors.HexColor(c) for c in ("#e5e5ea", "#f5f5f7", "#0071e3"))
POSITIVE, NEGATIVE, CAUTION = (colors.HexColor(c) for c in ("#1f8a4c", "#c9342b", "#b26a00"))
WIDTH = A4[0] - 36 * mm  # text width between the margins

_BASE = dict(fontName="Helvetica", textColor=INK, leading=13.5, fontSize=9.5)
S = {
    "body": ParagraphStyle("body", **_BASE),
    "soft": ParagraphStyle("soft", **{**_BASE, "textColor": SOFT}),
    "small": ParagraphStyle("small", **{**_BASE, "fontSize": 8, "leading": 10.5, "textColor": MUTED}),
    "tiny": ParagraphStyle("tiny", **{**_BASE, "fontSize": 7, "leading": 9, "textColor": MUTED}),
    "cell": ParagraphStyle("cell", **{**_BASE, "fontSize": 8.5, "leading": 11}),
    "cellb": ParagraphStyle("cellb", **{**_BASE, "fontSize": 8.5, "leading": 11, "fontName": "Helvetica-Bold"}),
    "cellr": ParagraphStyle("cellr", **{**_BASE, "fontSize": 8.5, "leading": 11, "alignment": TA_RIGHT}),
    "head": ParagraphStyle("head", **{**_BASE, "fontSize": 7.5, "leading": 10, "textColor": MUTED}),
    "headr": ParagraphStyle("headr", **{**_BASE, "fontSize": 7.5, "leading": 10, "textColor": MUTED,
                                         "alignment": TA_RIGHT}),
    "h1": ParagraphStyle("h1", **{**_BASE, "fontName": "Helvetica-Bold", "fontSize": 22, "leading": 26}),
    "h2": ParagraphStyle("h2", **{**_BASE, "fontName": "Helvetica-Bold", "fontSize": 13, "leading": 16,
                                   "spaceBefore": 14, "spaceAfter": 6}),
    "h3": ParagraphStyle("h3", **{**_BASE, "fontName": "Helvetica-Bold", "fontSize": 9.5, "leading": 12,
                                   "spaceBefore": 6, "spaceAfter": 2}),
    "kicker": ParagraphStyle("kicker", **{**_BASE, "fontSize": 8, "leading": 10, "textColor": MUTED}),
    "letter": ParagraphStyle("letter", **{**_BASE, "fontSize": 9.5, "leading": 14}),
}
_REPLACE = {"→": "->", "−": "-", "≥": ">=", "≤": "<=", "’": "'", "‘": "'",
            "“": '"', "”": '"', "–": "-", "—": "-", "…": "...", " ": " ",
            " ": " "}


def _t(value: Any) -> str:
    """Text made safe for the built-in PDF fonts (Windows-1252) and for ReportLab's markup."""
    text = str(value)
    for a, b in _REPLACE.items():
        text = text.replace(a, b)
    return escape(text.encode("cp1252", "replace").decode("cp1252"))


def P(text: Any, style: str = "body") -> Paragraph:
    return Paragraph(_t(text), S[style])


def M(markup: str, style: str = "body") -> Paragraph:
    """Paragraph from text that already contains ReportLab markup."""
    return Paragraph(markup, S[style])


def _pct(p: float, digits: int = 0) -> str:
    return f"{p * 100:.{digits}f}%"


def _hex(c: colors.Color) -> str:
    return "#" + c.hexval()[2:]


def _table(rows: list[list], widths: list[float], header: bool = True, extra: list | None = None,
           repeat: bool = True, split_rows: bool = False) -> Table:
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5),
             ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 4),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LINEBELOW", (0, 0), (-1, -2), 0.4, HAIRLINE)]
    if header:
        style += [("LINEBELOW", (0, 0), (-1, 0), 0.7, FAINT), ("BOTTOMPADDING", (0, 0), (-1, 0), 3)]
    table = Table(rows, colWidths=widths, repeatRows=1 if header and repeat else 0, splitInRow=1 if split_rows else 0)
    table.setStyle(TableStyle(style + (extra or [])))
    return table


# --------------------------------------------------------------------------- drawings
class RiskRuler(Flowable):
    """Default risk on a 0 to 100% scale against the refusal threshold: the visual device of the interface."""

    def __init__(self, value: float, threshold: float, margin: float = 0.0, width: float = WIDTH):
        super().__init__()
        self.value, self.threshold, self.margin, self.width, self.height = value, threshold, margin, width, 40

    def draw(self) -> None:
        c, w, y = self.canv, self.width, 14
        x = lambda p: max(0.0, min(1.0, p)) * w  # noqa: E731
        c.setFillColor(colors.Color(0.12, 0.54, 0.30, 0.22))
        c.roundRect(0, y, x(self.threshold), 6, 3, stroke=0, fill=1)
        c.setFillColor(colors.Color(0.79, 0.20, 0.17, 0.16))
        c.roundRect(x(self.threshold), y, w - x(self.threshold), 6, 3, stroke=0, fill=1)
        if self.margin:
            c.setFillColor(colors.Color(0.70, 0.42, 0.0, 0.30))
            c.rect(x(self.threshold - self.margin), y, x(self.threshold + self.margin) - x(self.threshold - self.margin),
                   6, stroke=0, fill=1)
        c.setStrokeColor(INK)
        c.setLineWidth(1)
        c.line(x(self.threshold), y - 4, x(self.threshold), y + 10)
        refused = self.value >= self.threshold
        c.setFillColor(NEGATIVE if refused else POSITIVE)
        c.circle(x(self.value), y + 3, 5, stroke=0, fill=1)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        c.drawString(0, 0, "0%")
        c.drawRightString(w, 0, "100%")
        label = f"Refusal threshold {_pct(self.threshold)}"
        tx = min(max(x(self.threshold), 45), w - 45)
        c.drawCentredString(tx, y + 16, label)
        c.setFillColor(NEGATIVE if refused else POSITIVE)
        c.setFont("Helvetica-Bold", 8)
        vx = min(max(x(self.value), 12), w - 12)
        c.drawCentredString(vx, 0, _pct(self.value, 1))


class FactorBars(Flowable):
    """Signed SHAP contributions: right of the axis raises the default risk, left lowers it."""

    ROW = 17

    def __init__(self, factors: list[dict], width: float = WIDTH):
        super().__init__()
        self.factors, self.width = factors, width
        self.height = self.ROW * len(factors) + 14

    def draw(self) -> None:
        c = self.canv
        label_w, value_w = 200, 44
        plot = self.width - label_w - value_w
        axis = label_w + plot / 2
        biggest = max((abs(f["contribution"]) for f in self.factors), default=1) or 1
        c.setFont("Helvetica", 7)
        c.setFillColor(MUTED)
        c.drawRightString(axis - 4, self.height - 8, "lowers the risk")
        c.drawString(axis + 4, self.height - 8, "raises the risk")
        c.setStrokeColor(FAINT)
        c.setLineWidth(0.5)
        c.line(axis, 0, axis, self.height - 12)
        for i, f in enumerate(self.factors):
            y = self.height - 14 - (i + 1) * self.ROW + 5
            c.setFillColor(INK)
            c.setFont("Helvetica", 8.5)
            text = f"{f['label']}: {f['value_label']}"
            while c.stringWidth(text, "Helvetica", 8.5) > label_w - 8 and len(text) > 8:
                text = text[:-4] + "..."
            c.drawString(0, y + 1, _plain(text))
            length = abs(f["contribution"]) / biggest * (plot / 2 - 4)
            up = f["contribution"] > 0
            c.setFillColor(NEGATIVE if up else POSITIVE)
            c.rect(axis if up else axis - length, y, length, 7, stroke=0, fill=1)
            c.setFillColor(SOFT)
            c.setFont("Helvetica", 8)
            c.drawRightString(self.width, y + 1, f"{f['contribution']:+.2f}")


class GroupBars(Flowable):
    """Approval rate of each group, one bar per group, on a common 0 to 100% scale."""

    ROW = 13

    def __init__(self, groups: dict[str, dict], width: float):
        super().__init__()
        self.groups, self.width = groups, width
        self.height = self.ROW * len(groups)

    def draw(self) -> None:
        c = self.canv
        label_w, value_w = 62, 58
        plot = self.width - label_w - value_w
        for i, (name, g) in enumerate(self.groups.items()):
            y = self.height - (i + 1) * self.ROW + 3
            c.setFont("Helvetica", 7.5)
            c.setFillColor(INK)
            c.drawString(0, y + 1, _plain(name.replace("_", " ")))
            c.setFillColor(HAIRLINE)
            c.rect(label_w, y, plot, 6, stroke=0, fill=1)
            c.setFillColor(FAINT if g["small_sample"] else INK)
            c.rect(label_w, y, plot * g["selection_rate"], 6, stroke=0, fill=1)
            c.setFillColor(MUTED)
            c.drawRightString(self.width, y + 1, f"{_pct(g['selection_rate'])}  (n={g['n']})")


def _plain(text: str) -> str:
    for a, b in _REPLACE.items():
        text = text.replace(a, b)
    return text.encode("cp1252", "replace").decode("cp1252")


class _Canvas(pdfcanvas.Canvas):
    """Second pass over the pages to print 'Page x of y' together with the report identity."""

    def __init__(self, *args, identity: dict[str, str], **kwargs):
        super().__init__(*args, **kwargs)
        self._identity = identity
        self._pages: list[dict] = []

    def showPage(self) -> None:
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._pages)
        for page in self._pages:
            self.__dict__.update(page)
            self._furniture(total)
            super().showPage()
        super().save()

    def _furniture(self, total: int) -> None:
        w, h = A4
        left, right = 18 * mm, w - 18 * mm
        i = self._identity
        self.setStrokeColor(HAIRLINE)
        self.setLineWidth(0.6)
        self.line(left, h - 15 * mm, right, h - 15 * mm)
        self.line(left, 14 * mm, right, 14 * mm)
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(INK)
        self.drawString(left, h - 12 * mm, "AgentForge Credit Audit")
        self.setFont("Helvetica", 8)
        self.setFillColor(MUTED)
        self.drawString(left + 108, h - 12 * mm, f"Audit report, applicant {i['applicant']}")
        self.drawRightString(right, h - 12 * mm, f"Report {i['report_id']}")
        self.setFont("Helvetica", 7.5)
        self.drawString(left, 10 * mm, f"Report {i['report_id']}   |   Generated {i['date']}   |   Model {i['model']}")
        self.drawRightString(right, 10 * mm, f"Page {self._pageNumber} of {total}")
        if i.get("draft"):
            self.setFillColor(CAUTION)
            self.setFont("Helvetica-Bold", 7.5)
            self.drawCentredString(w / 2, h - 12 * mm, i["draft"])


# --------------------------------------------------------------------------- content helpers
def _last(events: list[dict], key: str) -> Any:
    for e in reversed(events):
        if key in e.get("payload", {}):
            return e["payload"][key]
    return None


def fingerprint(application: dict | None, decision: AuditDecision, events: list[dict]) -> str:
    """SHA-256 of the audited content: the file, the decision and the trail of steps.

    The report path and identifier, the timestamps and the durations are left
    out, so the same audit always gives the same fingerprint.
    """
    steps = [{"node": e.get("node"), "status": e.get("status"), "mode": e.get("mode"), "message": e.get("message"),
              "tools": [(t.get("name"), t.get("result")) for t in e.get("tool_calls", [])
                        if t.get("name") not in ("render_report", "case_store.add")]} for e in events]
    body = {"application": application, "trail": steps,
            "decision": decision.model_dump(mode="json", exclude={"report_path", "report_id", "precedents"})}
    if body["decision"].get("review"):
        body["decision"]["review"] = {k: v for k, v in body["decision"]["review"].items() if k != "at"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _status_line(decision: AuditDecision) -> tuple[str, colors.Color, str]:
    """Headline, its colour and the sentence under it."""
    model = "Refused" if decision.decision == "refused" else "Approved"
    if decision.review:
        final = decision.final_outcome or decision.review.get("outcome")
        word = "Refused" if final == "refused" else "Approved"
        who = decision.review.get("reviewer") or "a reviewer"
        same = "confirming" if final == decision.decision else "overturning"
        return (f"{word} after human review", NEGATIVE if final == "refused" else POSITIVE,
                f"Decided by {who}, {same} the model's decision ({model.lower()}).")
    if decision.escalated:
        return (f"{model} by the model, waiting for human review", CAUTION,
                f"The agents did not close this file: {decision.escalation_reason}.")
    return (model, NEGATIVE if decision.decision == "refused" else POSITIVE,
            "Closed by the agents. No rule required a human review.")


def _file_section(app: LoanApplication) -> list:
    rows, current = [], None
    cells: list[list] = []
    for f in FEATURES:
        if f.group != current:
            if cells:
                rows.append(cells)
            current, cells = f.group, []
        value = f.label_of(getattr(app, f.name))
        mark = '  <font color="%s" size="7">protected</font>' % _hex(CAUTION) if f.protected else ""
        cells.append([M(f'<font color="{_hex(MUTED)}">{_t(f.label)}</font>{mark}', "cell"), P(value, "cell")])
    rows.append(cells)
    groups = [g for g in dict.fromkeys(f.group for f in FEATURES)]
    out: list = []
    half = (WIDTH - 10) / 2
    blocks = []
    for name, cells in zip(groups, rows):
        t = _table([[P(name, "cellb"), ""]] + cells, [half * 0.5, half * 0.5], header=True, repeat=False,
                   extra=[("SPAN", (0, 0), (1, 0))])
        blocks.append(t)
    grid = Table([[blocks[0], blocks[1]], [blocks[2], blocks[3]]], colWidths=[half + 5, half + 5])
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (0, -1), 10), ("RIGHTPADDING", (1, 0), (1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    out.append(grid)
    return out


def _ways_table(cfs: list[dict], before: float) -> Table:
    rows = [[P("#", "head"), P("Change requested from the applicant", "head"), P("Risk before", "headr"),
             P("Risk after", "headr"), P("Effort", "head"), P("Realism", "headr"), P("Found by", "head")]]
    for i, cf in enumerate(cfs, 1):
        plaus = cf.get("plausibility") or {}
        rows.append([
            P(i, "cell"), P(cf["statement"], "cell"), P(_pct(before), "cellr"),
            M(f'<font color="{_hex(POSITIVE)}"><b>{_pct(cf["new_probability"])}</b></font>', "cellr"),
            P("Now" if cf["effort"] == "immediate" else "Takes time", "cell"),
            P(_pct(plaus["score"]) if plaus else "", "cellr"),
            P("DiCE" if cf["source"] == "dice" else "Exhaustive search", "cell")])
    return _table(rows, [14, WIDTH - 14 - 48 - 46 - 52 - 42 - 76, 48, 46, 52, 42, 76])


def _attempts(events: list[dict]) -> list:
    out: list = []
    generator = [e for e in events if e["node"] == "generateur_contrefactuels"]
    auditor = [e for e in events if e["node"] == "verificateur_equite"]
    for i, g in enumerate(generator):
        verdict = auditor[i] if i < len(auditor) else None
        proposed = g.get("payload", {}).get("counterfactuals", [])
        kept = verdict.get("payload", {}).get("counterfactuals", []) if verdict else []
        rejected = verdict is not None and verdict["status"] == "rejected"
        colour = _hex(NEGATIVE if rejected else POSITIVE)
        word = "rejected by the auditor" if rejected else "accepted by the auditor"
        block = [M(f'<b>Attempt {i + 1}</b>  <font color="{colour}">{word}</font>'
                   f'  <font color="{_hex(MUTED)}">{len(proposed)} proposed, {len(kept)} kept</font>', "body"),
                 M(f'<font color="{_hex(MUTED)}">Plan ({_t(g["mode"])}):</font> {_t(g["message"])} {_t(g["reasoning"])}', "soft")]
        if verdict:
            block.append(M(f'<font color="{_hex(MUTED)}">Auditor:</font> {_t(verdict["message"])}', "soft"))
            reasons = (verdict.get("payload", {}).get("fairness") or {}).get("reasons", [])
            for r in reasons:
                if "sensitive attribute" in r:
                    continue
                block.append(M(f"&nbsp;&nbsp;&nbsp;- {_t(r[:1].upper() + r[1:])}", "small"))
        block.append(Spacer(1, 6))
        out.append(KeepTogether(block))
    return out


def _fairness(decision: AuditDecision) -> list:
    from app.tools.fairness import group_fairness_comparison  # computed on the test set, cached

    f = decision.fairness
    out: list = []
    if f is None:
        return [P("The fairness audit did not run.", "soft")]
    out.append(P("Individual test: is this decision the same when only a protected attribute changes?", "h3"))
    labels = {"sex": "Sex", "foreign_worker": "Foreign-worker status"}
    rows = [[P("Attribute changed, nothing else", "head"), P("Default risk moves by", "headr")]]
    for k, v in f.metrics.items():
        if k.startswith("flip_delta_"):
            rows.append([P(labels.get(k[11:], k[11:]), "cell"), P(f"{v * 100:+.1f} points", "cellr")])
    out.append(_table(rows, [WIDTH * 0.6, WIDTH * 0.4]))
    colour = _hex(POSITIVE if f.flip_test_passed else NEGATIVE)
    out.append(Spacer(1, 4))
    out.append(M(f'<font color="{colour}"><b>{"Passed" if f.flip_test_passed else "Failed"}.</b></font> '
                 + _t("The decision stays the same." if f.flip_test_passed else
                      "The decision changes with a protected attribute: a person must decide."), "body"))
    if f.verdict:
        out.append(Spacer(1, 3))
        out.append(M(f'<font color="{_hex(MUTED)}">Auditor\'s verdict:</font> {_t(f.verdict)}', "soft"))

    comparison = group_fairness_comparison()
    used = comparison["full"]["variant"] if decision.fairness is None else None  # noqa: F841
    out.append(P("Group test: does the model approve groups at different rates? (200 held-out files, Fairlearn)", "h3"))
    out.append(P("Approval rate per group, then the largest gap between two groups. The second model never sees sex, "
                 "age or foreign-worker status: what it still shows passes through correlated attributes.", "small"))
    out.append(Spacer(1, 4))
    col = (WIDTH - 70) / 2
    head = [P("", "head"), P("Audited model (all attributes)", "head"), P("Model without protected attributes", "head")]
    rows = [head]
    for attribute in ("sex", "age_group", "foreign_worker"):
        a, b = comparison["full"]["attributes"][attribute], comparison["unaware"]["attributes"][attribute]

        def cell(r: dict) -> list:
            ci = r["ci95"]["demographic_parity_difference"] if r.get("ci95") else None
            gap = (f'<b>Approval gap {r["demographic_parity_difference"] * 100:.0f} points</b>'
                   + (f' <font color="{_hex(MUTED)}">(95% interval {ci[0] * 100:.0f} to {ci[1] * 100:.0f})</font>' if ci else ""))
            small = any(g["small_sample"] for g in r["groups"].values())
            flag = (f' <font color="{_hex(MUTED)}">Too few files in one group to conclude.</font>' if small else
                    f' <font color="{_hex(CAUTION)}"><b>Above the {comparison["tolerance"] * 100:.0f}-point tolerance.</b></font>'
                    if r["alert"] else "")
            return [GroupBars(r["groups"], col - 12), Spacer(1, 3),
                    M(gap + flag, "small"),
                    M(f'Ratio {r["demographic_parity_ratio"]:.2f} (four-fifths rule: at least 0.80). '
                      f'Equalized odds gap {r["equalized_odds_difference"] * 100:.0f} points.', "small")]

        rows.append([P(a["label"], "cellb"), cell(a), cell(b)])
    out.append(_table(rows, [70, col, col]))
    for line in comparison["reading"]:
        out.append(M(f"- {_t(line)}", "small"))
    for note in f.notes:
        out.append(Spacer(1, 3))
        out.append(M(f'<font color="{_hex(CAUTION)}"><b>Attention point.</b></font> {_t(note)} '
                     "This describes the model, not this file: it is recorded for the reviewer and does not change the decision.",
                     "small"))
    return out


def _trail(events: list[dict]) -> list:
    out: list = []
    tone = {"rejected": NEGATIVE, "escalated": CAUTION, "error": NEGATIVE}
    rows = [[P("#", "head"), P("Agent and outcome of the step", "head"), P("Produced by", "head"), P("Time", "headr")]]
    for e in events:
        colour = _hex(tone.get(e["status"], INK))
        lines = [M(f'<b>{_t(e["agent"])}</b>  <font color="{colour}">{_t(e["status"])}</font>', "cell"),
                 P(e["message"], "cell")]
        for t in e.get("tool_calls", []):
            args = "; ".join(f"{k}: {', '.join(map(str, v)) if isinstance(v, list) else v}"
                             for k, v in (t.get("arguments") or {}).items())
            lines.append(M(f'<font name="Courier" size="7" color="{_hex(ACCENT)}">{_t(t["name"])}</font>'
                           f'<font size="7" color="{_hex(MUTED)}">({_t(args)})  {t.get("duration_ms", 0):.0f} ms</font>'
                           f'<br/><font size="7" color="{_hex(SOFT)}">&nbsp;&nbsp;= {_t(t.get("result", ""))}</font>', "tiny"))
        rows.append([P(e["seq"] + 1, "cell"), lines,
                     P("Language model" if e["mode"] == "llm" else "Rules", "cell"),
                     P(f'{e.get("duration_ms", 0):.0f} ms', "cellr")])
    out.append(_table(rows, [16, WIDTH - 16 - 62 - 42, 62, 42], split_rows=True))
    return out


# --------------------------------------------------------------------------- entry point
def render_report(decision: AuditDecision, events: list[dict], application: LoanApplication | None = None,
                  run_id: str | None = None, out_dir: Path | str | None = None) -> str | None:
    """Writes the PDF audit report and returns its path.

    decision      final AuditDecision of the audit (with the review when a person decided)
    events        the trail of the run: one record per agent step, with tool calls and payload
    application   the applicant file; without it the "Applicant file" section is left out
    """
    events = [e for e in events if e.get("node") != "system"]
    score = _last(events, "score")
    analysis = _last(events, "analysis")
    explanation = _last(events, "explanation")
    if score is None:
        return None
    now = datetime.now(timezone.utc)
    report_id = decision.report_id or f"AF-{now:%Y%m%d}-{(run_id or decision.applicant_id)[:8].upper()}"
    folder = Path(out_dir) if out_dir else data_dir("reports")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{report_id}.pdf"
    pending = decision.escalated and not decision.review
    identity = {"report_id": report_id, "applicant": decision.applicant_id, "model": score["model_version"],
                "date": f"{now:%d %b %Y, %H:%M} UTC", "draft": "INTERIM REPORT: WAITING FOR HUMAN REVIEW" if pending else ""}

    headline, tone, sentence = _status_line(decision)
    llm_steps = sum(1 for e in events if e["mode"] == "llm")
    story: list = [
        P("Credit decision audit report", "kicker"),
        P(f"Applicant {decision.applicant_id}", "h1"),
        Spacer(1, 6),
        M(f'<font color="{_hex(tone)}" size="15"><b>{_t(headline)}</b></font>', "body"),
        Spacer(1, 5),
        P(sentence, "soft"),
        Spacer(1, 10),
    ]
    facts = [
        ["Report", report_id, "Model", score["model_version"]],
        ["Run", run_id or "not recorded", "Refusal threshold", _pct(score["threshold"])],
        ["Generated", identity["date"], "Default risk", _pct(score["default_probability"], 1)],
        ["Agent steps", f"{len(events)} ({llm_steps} by the language model, {len(events) - llm_steps} by rules)",
         "Attempts", f"{decision.attempts} of {config.MAX_CF_ATTEMPTS}"],
    ]
    t = Table([[P(a, "head"), P(b, "cell"), P(c, "head"), P(d, "cell")] for a, b, c, d in facts],
              colWidths=[62, WIDTH / 2 - 62, 82, WIDTH / 2 - 82])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CANVAS), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(t)

    # 1. decision
    story += [P("1. Decision", "h2"),
              RiskRuler(score["default_probability"], score["threshold"], config.BORDERLINE_MARGIN), Spacer(1, 8),
              P(decision.summary, "body")]
    if explanation:
        story += [Spacer(1, 4), M(f'<font color="{_hex(MUTED)}">Explanation of the score:</font> {_t(explanation)}', "soft")]
    if analysis:
        story += [Spacer(1, 4), M(f'<font color="{_hex(MUTED)}">File check:</font> {_t(analysis["note"])}', "soft")]
    if decision.precedents:
        story.append(Spacer(1, 4))
        for p in decision.precedents:
            reviewed = " after human review" if p.reviewed else ""
            story.append(M(f'<font color="{_hex(MUTED)}">Similar file already audited:</font> {_t(p.applicant_id)}, '
                           f'{100 if p.similarity >= 1 else min(99, int(p.similarity * 100))}% similar, {_t(p.final_outcome)}{reviewed}, default risk '
                           f'{_pct(p.default_probability)} (run {_t(p.run_id)}).', "small"))
        if decision.precedent_conflict:
            story.append(M(f'<font color="{_hex(CAUTION)}"><b>Consistency:</b></font> '
                           f'{_t(decision.precedent_conflict)}.', "small"))

    # 2. file
    if application is not None:
        story.append(P("2. Applicant file", "h2"))
        story += _file_section(application)

    # 3. factors
    story.append(KeepTogether([
        P("3. Main factors of the score", "h2"),
        P("Exact SHAP contributions of the model, in log-odds. They add up to the score: nothing here is estimated "
          f"or written by a language model. An average applicant scores {_pct(score['base_probability'])}.", "small"),
        Spacer(1, 6), FactorBars(score["top_factors"])]))

    # 4. ways to approval
    story.append(P("4. Verified ways to approval", "h2"))
    cfs = [c.model_dump(mode="json") for c in decision.counterfactuals]
    if decision.decision == "approved":
        story.append(P("The file is approved: no way to approval had to be searched.", "soft"))
    elif cfs:
        story.append(P("Each proposal was re-scored by the model, checked against the recourse rules (protected and "
                       "fixed attributes untouched, amounts only down, situation only better), required to clear the "
                       "threshold with a safety margin, and compared with real past applicants. Realism is the share "
                       "of past files that are at least as isolated as the modified file.", "small"))
        story += [Spacer(1, 5), _ways_table(cfs, score["default_probability"])]
    else:
        last_try = next((e for e in reversed(events) if e["node"] == "generateur_contrefactuels"), None)
        miss = next((c for c in (last_try or {}).get("payload", {}).get("counterfactuals", [])
                     if not c["valid"] and c["actionable"]), None)
        text = "No realistic change brings this file under the threshold."
        if miss:
            stated = miss["statement"].rstrip(".")
            text += (f" With every permitted change applied ({stated[:1].lower() + stated[1:]}), "
                     f"the default risk would still be {_pct(miss['new_probability'])}.")
        story.append(P(text, "body"))

    # 5. attempts
    if any(e["node"] == "generateur_contrefactuels" for e in events):
        story.append(P("5. Attempts and rejected proposals", "h2"))
        story += _attempts(events)

    # 6. fairness
    story.append(P("6. Fairness", "h2"))
    story += _fairness(decision)

    # 7. human decision
    story.append(P("7. Human decision", "h2"))
    if decision.review:
        r = decision.review
        at = r.get("at", "")
        try:
            at = f"{datetime.fromisoformat(at):%d %b %Y, %H:%M} UTC"
        except ValueError:
            pass
        final = decision.final_outcome or r.get("outcome")
        rows = [[P("Reviewer", "head"), P(r.get("reviewer") or "Reviewer", "cell")],
                [P("Decision", "head"), M(f'<font color="{_hex(NEGATIVE if final == "refused" else POSITIVE)}">'
                                           f'<b>{_t(str(final).capitalize())}</b></font>', "cell")],
                [P("Recorded", "head"), P(at, "cell")],
                [P("Reason for review", "head"), P((decision.escalation_reason or "").capitalize() + ".", "cell")],
                [P("Reviewer's reason", "head"), P(r.get("comment") or "No comment recorded.", "cell")]]
        story.append(_table(rows, [100, WIDTH - 100], header=False))
    elif decision.escalated:
        story.append(M(f'<font color="{_hex(CAUTION)}"><b>Waiting for a reviewer.</b></font> '
                       f'{_t((decision.escalation_reason or "").capitalize())}. The run is suspended on its checkpoint '
                       "and resumes when the reviewer answers; this report is then issued again with the decision.", "body"))
    else:
        story.append(P("None: no rule required a human review for this file.", "soft"))

    # 8. trail
    story.append(P("8. Agent trail", "h2"))
    story.append(P("Every step of the audit in order, with the tools it called, their arguments, their results and "
                   "their duration. Numbers in this report come from these tool calls.", "small"))
    story.append(Spacer(1, 5))
    story += _trail(events)

    # 9. letter
    if decision.letter:
        story.append(PageBreak())
        story.append(P("9. Applicant letter", "h2"))
        status = ("Draft, not to be sent: the reviewer has not decided yet." if decision.letter_status == "draft"
                  else "Final version, in French, written from the tool outputs only.")
        story.append(M(f'<font color="{_hex(CAUTION if decision.letter_status == "draft" else MUTED)}">{status}</font>', "small"))
        story.append(Spacer(1, 6))
        body = [M(_t(line) if line.strip() else "&nbsp;", "letter") for line in decision.letter.split("\n")]
        box = Table([[body]], colWidths=[WIDTH])
        box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, HAIRLINE), ("LEFTPADDING", (0, 0), (-1, -1), 16),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 16), ("TOPPADDING", (0, 0), (-1, -1), 14),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 14)]))
        story.append(box)

    # 10. integrity
    digest = fingerprint(application.features() if application else None, decision, events)
    story.append(P("10. Integrity and limits", "h2"))
    story.append(M(f'<font color="{_hex(MUTED)}">Fingerprint (SHA-256 of the file, the decision and the trail):</font><br/>'
                   f'<font name="Courier" size="8">{digest}</font>', "small"))
    story.append(Spacer(1, 4))
    for line in (
        "The fingerprint changes if the file, the decision, a step or a tool result is altered after the audit.",
        "The model is trained on the Statlog German Credit data (1,000 files, one German bank, amounts in Deutsche Mark): "
        "a benchmark, not a production portfolio.",
        "A way to approval states what the model would decide for the modified file. It is not a promise of approval "
        "nor a causal guarantee of repayment.",
        "Group metrics are measured on 200 held-out files: their intervals are wide and are printed with them.",
    ):
        story.append(M(f"- {_t(line)}", "small"))

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=21 * mm,
                            bottomMargin=19 * mm, title=f"Audit report {report_id}", author="AgentForge Credit Audit",
                            subject=f"Applicant {decision.applicant_id}")
    doc.build(story, canvasmaker=lambda *a, **k: _Canvas(*a, identity=identity, **k))
    return str(path)
