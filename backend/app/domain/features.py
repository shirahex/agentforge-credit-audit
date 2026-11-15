"""Applicant attributes of the Statlog German Credit dataset.

Single source of truth for labels, category order, value ranges and the
recourse rules attached to each attribute. The data preparation, the model
encoder, the counterfactual search, the API schema endpoint and the
interface form are all driven by this file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["numeric", "categorical", "boolean"]
# How an applicant can act on an attribute:
#   request      term of the loan request, changeable immediately
#   situation    financial situation, improvable over months
#   fixed        cannot be changed by the applicant, or must never be suggested
Recourse = Literal["request", "situation", "fixed"]


@dataclass(frozen=True)
class Feature:
    name: str
    label: str
    kind: Kind
    group: str
    recourse: Recourse = "fixed"
    # categorical: ordered list of (value, label, original UCI code)
    categories: tuple[tuple[str, str, str], ...] = ()
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    protected: bool = False
    # Allowed direction of change for recourse: -1 decrease, +1 increase, 0 any.
    direction: int = 0
    # For ordered categoricals: values that can be reached by improving, in order.
    ladder: tuple[str, ...] = field(default=())

    @property
    def values(self) -> list[str]:
        return [c[0] for c in self.categories]

    def label_of(self, value) -> str:
        if self.kind == "categorical":
            return next((c[1] for c in self.categories if c[0] == value), str(value))
        if self.kind == "boolean":
            return "Yes" if value else "No"
        if not isinstance(value, (int, float)):
            return str(value)
        if self.unit.startswith("level"):
            return f"level {value:g} of {self.maximum:g}"
        return f"{value:,} {self.unit}".strip() if self.unit == "DM" else f"{value:g} {self.unit}".strip()


FEATURES: tuple[Feature, ...] = (
    # ---- loan request
    Feature("credit_amount", "Credit amount", "numeric", "Loan request", "request",
            unit="DM", minimum=250, maximum=20000, direction=-1),
    Feature("duration_months", "Duration", "numeric", "Loan request", "request",
            unit="months", minimum=4, maximum=72, direction=-1),
    Feature("purpose", "Purpose", "categorical", "Loan request", "fixed", categories=(
        ("car_new", "New car", "A40"), ("car_used", "Used car", "A41"),
        ("furniture", "Furniture or equipment", "A42"), ("radio_tv", "Radio or television", "A43"),
        ("appliances", "Domestic appliances", "A44"), ("repairs", "Repairs", "A45"),
        ("education", "Education", "A46"), ("retraining", "Retraining", "A48"),
        ("business", "Business", "A49"), ("other", "Other", "A410"))),
    Feature("installment_rate", "Instalment rate (share of income)", "numeric", "Loan request",
            "fixed", unit="level 1 to 4", minimum=1, maximum=4),
    Feature("other_debtors", "Co-applicant or guarantor", "categorical", "Loan request", "request",
            categories=(("none", "None", "A101"), ("co_applicant", "Co-applicant", "A102"),
                        ("guarantor", "Guarantor", "A103")),
            ladder=("none", "guarantor")),
    # ---- financial situation
    Feature("checking_status", "Checking account", "categorical", "Financial situation", "situation",
            categories=(("negative", "Overdrawn (below 0 DM)", "A11"), ("low", "0 to 200 DM", "A12"),
                        ("high", "200 DM or more, or salary account", "A13"),
                        ("no_account", "No checking account", "A14")),
            ladder=("negative", "low", "high")),
    Feature("savings", "Savings", "categorical", "Financial situation", "situation",
            categories=(("lt_100", "Below 100 DM", "A61"), ("100_to_500", "100 to 500 DM", "A62"),
                        ("500_to_1000", "500 to 1,000 DM", "A63"), ("ge_1000", "1,000 DM or more", "A64"),
                        ("unknown", "Unknown or no savings account", "A65")),
            ladder=("lt_100", "100_to_500", "500_to_1000", "ge_1000")),
    Feature("credit_history", "Credit history", "categorical", "Financial situation", "fixed", categories=(
        ("no_credits", "No credit taken", "A30"), ("all_paid_here", "All credits at this bank repaid", "A31"),
        ("existing_paid", "Existing credits repaid on time so far", "A32"),
        ("past_delays", "Delays in the past", "A33"),
        ("critical", "Critical account or credits elsewhere", "A34"))),
    Feature("existing_credits", "Existing credits at this bank", "numeric", "Financial situation", "situation",
            minimum=1, maximum=4, direction=-1),
    Feature("other_installment_plans", "Other instalment plans", "categorical", "Financial situation",
            "situation", categories=(("bank", "At another bank", "A141"), ("stores", "At stores", "A142"),
                                     ("none", "None", "A143")),
            ladder=("bank", "none"),),
    Feature("property", "Most valuable property", "categorical", "Financial situation", "fixed", categories=(
        ("real_estate", "Real estate", "A121"), ("savings_insurance", "Building society savings or life insurance", "A122"),
        ("car_other", "Car or other", "A123"), ("none", "Unknown or none", "A124"))),
    # ---- employment and housing
    Feature("employment", "Time in current employment", "categorical", "Employment and housing", "fixed",
            categories=(("unemployed", "Unemployed", "A71"), ("lt_1y", "Less than 1 year", "A72"),
                        ("1_to_4y", "1 to 4 years", "A73"), ("4_to_7y", "4 to 7 years", "A74"),
                        ("ge_7y", "7 years or more", "A75"))),
    Feature("job", "Job level", "categorical", "Employment and housing", "fixed", categories=(
        ("unskilled_non_resident", "Unemployed or unskilled, non-resident", "A171"),
        ("unskilled_resident", "Unskilled, resident", "A172"),
        ("skilled", "Skilled employee or official", "A173"),
        ("highly_skilled", "Management, self-employed or highly qualified", "A174"))),
    Feature("housing", "Housing", "categorical", "Employment and housing", "fixed", categories=(
        ("rent", "Rent", "A151"), ("own", "Own", "A152"), ("free", "Free of charge", "A153"))),
    Feature("residence_since", "Years at current residence", "numeric", "Employment and housing", "fixed",
            unit="level 1 to 4", minimum=1, maximum=4),
    Feature("telephone", "Registered telephone", "boolean", "Employment and housing", "fixed"),
    # ---- personal
    Feature("age", "Age", "numeric", "Personal", "fixed", unit="years", minimum=18, maximum=80, protected=True),
    Feature("sex", "Sex", "categorical", "Personal", "fixed", protected=True,
            categories=(("male", "Male", ""), ("female", "Female", ""))),
    Feature("dependents", "Dependents", "numeric", "Personal", "fixed", minimum=1, maximum=2),
    Feature("foreign_worker", "Foreign worker", "boolean", "Personal", "fixed", protected=True),
)

BY_NAME: dict[str, Feature] = {f.name: f for f in FEATURES}
PROTECTED: tuple[str, ...] = tuple(f.name for f in FEATURES if f.protected)
ACTIONABLE: tuple[str, ...] = tuple(f.name for f in FEATURES if f.recourse != "fixed")

# Model variants. "full" is the model under audit and uses every attribute,
# as a legacy scorecard would. "unaware" removes the protected attributes.
VARIANT_FEATURES: dict[str, tuple[str, ...]] = {
    "full": tuple(f.name for f in FEATURES),
    "unaware": tuple(f.name for f in FEATURES if not f.protected),
}

# Risk can only grow with these attributes (LightGBM monotone constraints).
MONOTONE_INCREASING: tuple[str, ...] = ("duration_months", "credit_amount", "installment_rate")


def describe() -> list[dict]:
    """Metadata served to the interface to build the applicant form."""
    return [
        {
            "name": f.name, "label": f.label, "kind": f.kind, "group": f.group, "unit": f.unit,
            "min": f.minimum, "max": f.maximum, "protected": f.protected, "recourse": f.recourse,
            "options": [{"value": v, "label": lab} for v, lab, _ in f.categories],
        }
        for f in FEATURES
    ]
