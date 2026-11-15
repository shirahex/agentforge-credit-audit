"""French wording of the applicant attributes, for the applicant letter (task I2).

The interface and the audit trail are in English; the letter sent to the
applicant is in French. Labels are kept next to the attribute dictionary so
that a new attribute or category cannot be forgotten: `check()` is run by
the tests.
"""
from __future__ import annotations

from typing import Any

from app.domain.features import BY_NAME, FEATURES

LABELS: dict[str, str] = {
    "credit_amount": "le montant demandé",
    "duration_months": "la durée de remboursement",
    "purpose": "l'objet du crédit",
    "installment_rate": "le poids des mensualités dans vos revenus",
    "other_debtors": "la présence d'un co-emprunteur ou d'un garant",
    "checking_status": "la situation de votre compte courant",
    "savings": "le niveau de votre épargne",
    "credit_history": "votre historique de crédit",
    "existing_credits": "le nombre de crédits en cours dans notre établissement",
    "other_installment_plans": "vos autres crédits à tempérament",
    "property": "votre patrimoine",
    "employment": "votre ancienneté dans l'emploi actuel",
    "job": "votre catégorie professionnelle",
    "housing": "votre situation de logement",
    "residence_since": "votre ancienneté dans le logement actuel",
    "telephone": "l'enregistrement d'une ligne téléphonique",
    "age": "l'âge",
    "sex": "le sexe",
    "dependents": "le nombre de personnes à charge",
    "foreign_worker": "le statut de travailleur étranger",
}

VALUES: dict[str, dict[Any, str]] = {
    "purpose": {"car_new": "voiture neuve", "car_used": "voiture d'occasion", "furniture": "mobilier ou équipement",
                "radio_tv": "radio ou télévision", "appliances": "électroménager", "repairs": "travaux",
                "education": "études", "retraining": "reconversion", "business": "activité professionnelle",
                "other": "autre"},
    "other_debtors": {"none": "aucun", "co_applicant": "co-emprunteur", "guarantor": "garant"},
    "checking_status": {"negative": "à découvert", "low": "solde entre 0 et 200 DM",
                        "high": "solde de 200 DM ou plus, ou compte de domiciliation du salaire",
                        "no_account": "pas de compte courant"},
    "savings": {"lt_100": "moins de 100 DM", "100_to_500": "entre 100 et 500 DM",
                "500_to_1000": "entre 500 et 1 000 DM", "ge_1000": "1 000 DM ou plus",
                "unknown": "inconnue ou pas de compte d'épargne"},
    "credit_history": {"no_credits": "aucun crédit contracté",
                       "all_paid_here": "tous les crédits de notre établissement remboursés",
                       "existing_paid": "crédits en cours remboursés sans retard",
                       "past_delays": "retards de paiement par le passé",
                       "critical": "compte sensible ou crédits dans d'autres établissements"},
    "other_installment_plans": {"bank": "dans une autre banque", "stores": "auprès de magasins", "none": "aucun"},
    "property": {"real_estate": "bien immobilier", "savings_insurance": "épargne logement ou assurance-vie",
                 "car_other": "véhicule ou autre bien", "none": "inconnu ou aucun"},
    "employment": {"unemployed": "sans emploi", "lt_1y": "moins d'un an", "1_to_4y": "de 1 à 4 ans",
                   "4_to_7y": "de 4 à 7 ans", "ge_7y": "7 ans ou plus"},
    "job": {"unskilled_non_resident": "sans emploi ou non qualifié, non résident",
            "unskilled_resident": "non qualifié, résident", "skilled": "employé qualifié ou fonctionnaire",
            "highly_skilled": "cadre, indépendant ou hautement qualifié"},
    "housing": {"rent": "locataire", "own": "propriétaire", "free": "logé à titre gratuit"},
    "sex": {"male": "homme", "female": "femme"},
}

MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre")


def amount(value: int | float) -> str:
    """4500 -> '4 500 DM' (French thousands separator)."""
    return f"{int(value):,}".replace(",", " ") + " DM"


def date(d) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def value_label(feature: str, value: Any) -> str:
    f = BY_NAME[feature]
    if f.kind == "categorical":
        return VALUES[feature][value]
    if f.kind == "boolean":
        return "oui" if value else "non"
    if feature == "credit_amount":
        return amount(value)
    if feature == "duration_months":
        return f"{value} mois"
    if f.unit.startswith("level"):
        return f"niveau {value} sur {f.maximum:g}"
    if feature == "age":
        return f"{value} ans"
    return str(value)


def factor(feature: str, value: Any) -> str:
    """'la durée de remboursement (48 mois)'"""
    return f"{LABELS[feature]} ({value_label(feature, value)})"


def change(feature: str, current: Any, new: Any) -> str:
    """One requested change, as an action the applicant can take."""
    if feature == "credit_amount":
        return f"demander {amount(new)} au lieu de {amount(current)}"
    if feature == "duration_months":
        return f"rembourser sur {new} mois au lieu de {current}"
    if feature == "other_debtors" and new == "guarantor":
        return "présenter un garant"
    if feature == "other_debtors":
        return f"présenter un {VALUES[feature][new]}"
    if feature == "existing_credits":
        return f"solder un crédit en cours dans notre établissement (de {current} à {new})"
    if feature == "other_installment_plans" and new == "none":
        return "solder vos autres crédits à tempérament"
    if feature == "checking_status":
        return f"ramener votre compte courant à la situation « {VALUES[feature][new]} »"
    if feature == "savings":
        return f"porter votre épargne à « {VALUES[feature][new]} »"
    return f"faire passer {LABELS[feature]} de « {value_label(feature, current)} » à « {value_label(feature, new)} »"


def path(changes: list[tuple[str, Any, Any]]) -> str:
    text = " ; ".join(change(f, a, b) for f, a, b in changes)
    return text[:1].upper() + text[1:]


def check() -> list[str]:
    """Attributes or categories without a French wording."""
    missing = [f.name for f in FEATURES if f.name not in LABELS]
    for f in FEATURES:
        if f.kind == "categorical":
            missing += [f"{f.name}={v}" for v in f.values if v not in VALUES.get(f.name, {})]
    return missing
