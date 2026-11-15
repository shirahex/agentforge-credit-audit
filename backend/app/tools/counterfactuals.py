"""Counterfactual tools (task M3).

Two generators feed the Générateur-Contrefactuels agent:

* `exhaustive_search`: enumerates every combination of up to `max_changes`
  permitted moves (smaller amount, shorter duration, guarantor, better
  savings or account standing, fewer running credits), scores them in one
  model call and keeps the cheapest valid combination for each set of
  attributes. Deterministic and complete on the permitted space.
* `dice_search`: DiCE (random sampling) on the same attributes, used as an
  independent second source. DiCE ignores direction rules, so its proposals
  go through `check_actionability` like any other candidate.

Every candidate is re-scored by the model. `valid` means the decision
really flips; `robust` means it flips with a safety margin.
"""
from __future__ import annotations

import contextlib
import io
import itertools
import math
import os
import warnings
from typing import Any, Iterable

import pandas as pd

from app import config
from app.domain.features import ACTIONABLE, BY_NAME, VARIANT_FEATURES
from app.schemas import Counterfactual, FeatureChange, LoanApplication
from app.tools import scoring

REQUEST_SCOPE = tuple(n for n in ACTIONABLE if BY_NAME[n].recourse == "request")
# Relative effort of one step on each attribute, used to rank candidates.
STEP_COST = {"other_debtors": 0.45, "savings": 0.5, "checking_status": 0.6,
             "other_installment_plans": 0.55, "existing_credits": 0.55}
NUMERIC_COST = {"credit_amount": 1.0, "duration_months": 0.8}


# --------------------------------------------------------------------------- rules
def permitted_moves(app: LoanApplication, features: Iterable[str] | None = None,
                    widen: bool = False) -> dict[str, list[Any]]:
    """Values each actionable attribute may take for this applicant."""
    wanted = [f for f in (features or ACTIONABLE) if f in ACTIONABLE]
    floor = 0.4 if widen else 0.55  # a request cut by more than this no longer serves its purpose
    moves: dict[str, list[Any]] = {}
    for name in wanted:
        f, current = BY_NAME[name], getattr(app, name)
        if name == "credit_amount":
            steps = [0.9, 0.8, 0.7, 0.6] + ([0.5, 0.4] if widen else [])
            vals = sorted({max(int(f.minimum), int(round(current * s / 50.0) * 50)) for s in steps
                           if current * s >= current * floor}, reverse=True)
            moves[name] = [v for v in vals if current * floor <= v < current]
        elif name == "duration_months":
            lowest = max(int(f.minimum), math.ceil(current * floor))
            step = 6 if current > 12 else 3
            vals = list(range(current - step, lowest - 1, -step))
            moves[name] = [v for v in vals if v >= f.minimum]
        elif name == "existing_credits":
            moves[name] = [current - 1] if current > 1 else []
        elif f.ladder:
            moves[name] = list(f.ladder[f.ladder.index(current) + 1:]) if current in f.ladder else []
    return {k: v for k, v in moves.items() if v}


def check_actionability(app: LoanApplication, changes: dict[str, Any]) -> tuple[bool, str | None]:
    """Recourse rules: fixed and protected attributes, direction, bounds."""
    for name, new in changes.items():
        f, current = BY_NAME[name], getattr(app, name)
        if f.protected:
            return False, f"changes a protected attribute ({f.label.lower()})"
        if f.recourse == "fixed":
            return False, f"changes an attribute the applicant cannot act on ({f.label.lower()})"
        if f.kind == "numeric":
            if f.direction == -1 and new > current:
                return False, f"asks to increase {f.label.lower()}"
            if new < f.minimum or new > f.maximum:
                return False, f"{f.label.lower()} outside the permitted range"
            if name in NUMERIC_COST and new < current * 0.4:
                return False, f"cuts {f.label.lower()} by more than 60%"
        elif f.ladder:
            if current not in f.ladder or new not in f.ladder:
                return False, f"{f.label.lower()} cannot be moved to \"{f.label_of(new)}\""
            if f.ladder.index(new) <= f.ladder.index(current):
                return False, f"worsens {f.label.lower()}"
    return True, None


def change_cost(app: LoanApplication, changes: dict[str, Any]) -> float:
    total = 0.12 * (len(changes) - 1)
    for name, new in changes.items():
        f, current = BY_NAME[name], getattr(app, name)
        if name in NUMERIC_COST:
            total += NUMERIC_COST[name] * abs(current - new) / max(current, 1)
        elif name == "existing_credits":
            total += STEP_COST[name] * abs(current - new)
        elif f.ladder and current in f.ladder and new in f.ladder:
            total += STEP_COST.get(name, 0.6) * abs(f.ladder.index(new) - f.ladder.index(current))
        else:
            total += 1.0
    return round(total, 4)


def describe(app: LoanApplication, changes: dict[str, Any]) -> tuple[list[FeatureChange], str]:
    items, parts = [], []
    for name, new in changes.items():
        f, current = BY_NAME[name], getattr(app, name)
        fc = FeatureChange(feature=name, label=f.label, from_value=current, to_value=new,
                           from_label=f.label_of(current), to_label=f.label_of(new))
        items.append(fc)
        improving = check_actionability(app, {name: new})[0]
        if name == "credit_amount":
            parts.append(f"request {new:,} DM instead of {current:,} DM")
        elif name == "duration_months":
            parts.append(f"repay over {new} months instead of {current}")
        elif name == "other_debtors" and new == "guarantor":
            parts.append("add a guarantor")
        elif name == "existing_credits" and improving:
            parts.append(f"close one running credit at this bank ({current} to {new})")
        elif name == "other_installment_plans" and new == "none":
            parts.append("settle the other instalment plans")
        elif f.kind == "categorical":
            parts.append(f"bring {f.label.lower()} to \"{fc.to_label}\"")
        else:
            parts.append(f"change {f.label.lower()} from {current} to {new}")
    text = "; ".join(parts)
    return items, text[:1].upper() + text[1:] + "."


def build(app: LoanApplication, changes: dict[str, Any], new_p: float, source: str) -> Counterfactual:
    thr = scoring.threshold()
    actionable, reason = check_actionability(app, changes)
    items, statement = describe(app, changes)
    valid = new_p < thr
    if actionable and not valid:
        reason = "decision does not flip after re-scoring"
    medium = any(BY_NAME[n].recourse == "situation" for n in changes)
    return Counterfactual(
        changes=items, new_probability=round(float(new_p), 4), valid=valid, actionable=actionable,
        rejection_reason=reason, robust=valid and new_p <= thr - config.ROBUST_MARGIN,
        effort="medium_term" if medium else "immediate", cost=change_cost(app, changes),
        source=source, statement=statement,
    )


# --------------------------------------------------------------------------- generators
def exhaustive_search(app: LoanApplication, features: Iterable[str] | None = None, max_changes: int = 2,
                      widen: bool = False) -> list[Counterfactual]:
    moves = permitted_moves(app, features, widen)
    base = app.features()
    combos: list[dict[str, Any]] = []
    names = list(moves)
    for k in range(1, min(max_changes, len(names)) + 1):
        for subset in itertools.combinations(names, k):
            for values in itertools.product(*(moves[n] for n in subset)):
                combos.append(dict(zip(subset, values)))
    if not combos:
        return []
    probs = scoring.probabilities({**base, **c} for c in combos)
    thr = scoring.threshold()
    # Cheapest valid combination per set of attributes, preferring robust ones.
    best: dict[tuple, tuple[float, dict, float]] = {}
    for c, p in zip(combos, probs):
        if p >= thr:
            continue
        robust = p <= thr - config.ROBUST_MARGIN
        rank = change_cost(app, c) + (0 if robust else 0.5)
        key = tuple(sorted(c))
        if key not in best or rank < best[key][0]:
            best[key] = (rank, c, float(p))
    kept = sorted(best.values(), key=lambda t: t[0])
    # A larger set is only worth keeping when it is cheaper than its subsets.
    out: list[tuple[float, dict, float]] = []
    for rank, c, p in kept:
        if any(set(o[1]) < set(c) and o[0] <= rank for o in out):
            continue
        out.append((rank, c, p))
    return [build(app, c, p, "exhaustive") for _, c, p in out]


def closest_miss(app: LoanApplication, features: Iterable[str] | None = None, widen: bool = False) -> Counterfactual | None:
    """Best permitted combination when nothing flips the decision: how far the applicant can get."""
    moves = permitted_moves(app, features, widen)
    if not moves:
        return None
    base = app.features()
    strongest = {n: v[-1] for n, v in moves.items()}
    p = float(scoring.probabilities([{**base, **strongest}])[0])
    return build(app, strongest, p, "exhaustive")


_DICE: dict[str, tuple] = {}


def _dice_explainer():
    m = scoring.model()
    if m.variant not in _DICE:
        os.environ.setdefault("TQDM_DISABLE", "1")  # DiCE prints a progress bar per query
        import dice_ml  # heavy import, only when the second generator is used
        from app.domain.model import ROOT

        feats = list(VARIANT_FEATURES[m.variant])
        train = pd.read_csv(ROOT / "ml" / "data" / "processed" / "train.csv")[feats + ["default"]]
        continuous = [f for f in feats if BY_NAME[f].kind == "numeric"]
        data = dice_ml.Data(dataframe=train, continuous_features=continuous, outcome_name="default")
        _DICE[m.variant] = (dice_ml.Dice(data, dice_ml.Model(model=m, backend="sklearn"), method="random"), feats)
    return _DICE[m.variant]


def dice_search(app: LoanApplication, features: Iterable[str] | None = None, total: int = 4,
                seed: int = 7) -> list[Counterfactual]:
    wanted = [f for f in (features or ACTIONABLE) if f in ACTIONABLE]
    try:
        explainer, feats = _dice_explainer()
        query = pd.DataFrame([{k: v for k, v in app.features().items() if k in feats}])[feats]
        with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter("ignore")
            result = explainer.generate_counterfactuals(
                query, total_CFs=total, desired_class=0, features_to_vary=wanted, random_seed=seed,
                stopping_threshold=1 - scoring.threshold() + config.ROBUST_MARGIN, verbose=False)
        frame = result.cf_examples_list[0].final_cfs_df
    except Exception:  # DiCE finds nothing or fails: the exhaustive generator still answers
        return []
    if frame is None or frame.empty:
        return []
    base, out, seen = app.features(), [], set()
    for _, row in frame.iterrows():
        changes = {}
        for name in wanted:
            new = row[name]
            if BY_NAME[name].kind == "numeric":
                new = int(round(float(new)))
                if name == "credit_amount":
                    new = int(round(new / 50.0) * 50)
                    if abs(new - base[name]) < 50:  # rounding noise, not a real change
                        new = base[name]
            if new != base[name]:
                changes[name] = new
        key = tuple(sorted(changes.items()))
        if not changes or key in seen:
            continue
        seen.add(key)
        p = float(scoring.probabilities([{**base, **changes}])[0])
        out.append(build(app, changes, p, "dice"))
    return out


def generate_counterfactuals(app: LoanApplication, features: Iterable[str] | None = None, max_changes: int = 2,
                             widen: bool = False, use_dice: bool = True, limit: int = 4) -> list[Counterfactual]:
    """Candidates from both generators: valid and actionable first, cheapest first."""
    found = exhaustive_search(app, features, max_changes, widen)
    if use_dice:
        known = {tuple(sorted((c.feature, c.to_value) for c in cf.changes)) for cf in found}
        for cf in dice_search(app, features):
            key = tuple(sorted((c.feature, c.to_value) for c in cf.changes))
            if key not in known:
                known.add(key)
                found.append(cf)
    good = sorted((c for c in found if c.valid and c.actionable), key=lambda c: (not c.robust, c.cost))
    bad = [c for c in found if not (c.valid and c.actionable)]
    # Keep variety: at most two candidates per effort level in the first places.
    picked: list[Counterfactual] = []
    for cf in good:
        if len(picked) < limit and sum(1 for p in picked if {c.feature for c in p.changes} == {c.feature for c in cf.changes}) == 0:
            picked.append(cf)
    return picked + bad[:2]
