"""Agent graph. Owner: Imane (task I3).

    analyste_dossier -> modele_scoring -+-> generateur_contrefactuels -> verificateur_equite -+-> arbitre_redacteur
                                        |            ^                                        |
                                        |            +---- rejected, attempts left -----------+
                                        +-> (approved) verificateur_equite

TODO: checkpointer, human interrupt before finalisation, re-analysis loop
towards the Analyste-Dossier when the file is inconsistent.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app import config
from app.agents import (
    analyste_dossier,
    arbitre_redacteur,
    generateur_contrefactuels,
    modele_scoring,
    verificateur_equite,
)
from app.graph.state import AuditState

AGENT_LABELS = {
    "analyste_dossier": "Analyste-Dossier",
    "modele_scoring": "Modèle-Scoring",
    "generateur_contrefactuels": "Générateur-Contrefactuels",
    "verificateur_equite": "Vérificateur-Équité",
    "arbitre_redacteur": "Arbitre et Rédacteur",
}


def _after_scoring(state: AuditState) -> str:
    return "generateur_contrefactuels" if state["score"].decision == "refused" else "verificateur_equite"


def _after_audit(state: AuditState) -> str:
    refused = state["score"].decision == "refused"
    no_cf = not state.get("counterfactuals")
    if refused and no_cf and state.get("attempts", 0) < config.MAX_CF_ATTEMPTS:
        return "generateur_contrefactuels"
    return "arbitre_redacteur"


def build_graph():
    g = StateGraph(AuditState)
    g.add_node("analyste_dossier", analyste_dossier.run)
    g.add_node("modele_scoring", modele_scoring.run)
    g.add_node("generateur_contrefactuels", generateur_contrefactuels.run)
    g.add_node("verificateur_equite", verificateur_equite.run)
    g.add_node("arbitre_redacteur", arbitre_redacteur.run)

    g.add_edge(START, "analyste_dossier")
    g.add_edge("analyste_dossier", "modele_scoring")
    g.add_conditional_edges(
        "modele_scoring", _after_scoring, ["generateur_contrefactuels", "verificateur_equite"]
    )
    g.add_edge("generateur_contrefactuels", "verificateur_equite")
    g.add_conditional_edges(
        "verificateur_equite", _after_audit, ["generateur_contrefactuels", "arbitre_redacteur"]
    )
    g.add_edge("arbitre_redacteur", END)
    return g.compile()


graph = build_graph()
