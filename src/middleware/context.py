"""middleware/context.py — Objet de contexte partagé entre tous les steps."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Context:
    """
    Objet mutable passé de step en step dans le pipeline.
    Chaque step peut lire, enrichir ou modifier ces données.
    """

    # ── Email source ───────────────────────────────────────────────────────
    email_id: str = ""
    email_subject: str = ""
    email_sender: str = ""
    email_sender_address: str = ""
    email_received_at: str = ""
    email_body: str = ""
    email_body_preview: str = ""
    email_to_recipients: list[str] = field(default_factory=list)
    has_attachments: bool = False
    attachments: list[dict] = field(default_factory=list)

    # ── Données extraites par l'IA ─────────────────────────────────────────
    client_data: dict = field(default_factory=dict)

    # ── CRM Dolibarr ──────────────────────────────────────────────────────
    socid: int | None = None
    soc_nom: str = ""
    nom_projet: str = ""
    client_created: bool = False
    devis_id: int | None = None
    devis_ref: str = ""

    # ── Analyse besoin impression ──────────────────────────────────────────
    synthese_contexte: str = ""
    date_livraison_souhaitee: str | None = None
    composants_isoles: list[dict] = field(default_factory=list)

    # ── Devis construit ────────────────────────────────────────────────────
    devis_lines: list[dict] = field(default_factory=list)

    # ── Skills IA enrichis (s02) ───────────────────────────────────────────
    email_sentiment: dict = field(default_factory=dict)
    # ex: {"sentiment": "positif|neutre|négatif|agressif",
    #      "urgence": "faible|modérée|critique",
    #      "profil": "formel|décontracté|anxieux|exigeant|bienveillant",
    #      "intention": "demande_devis|demande_info|réclamation|relance|autre"}
    routing_category: str = ""
    # ex: "NEW_PROJECT|VISUAL_CREATION|SUPPLIER_INVOICE|PROJECT_UPDATE|..."
    email_reponse_client: str = ""
    # généré par s12 (CONFIG_CLIENT_v2026)

    # ── Sorties structurées (output_builder — s12) ────────────────────────
    output_response: dict = field(default_factory=dict)
    # ex: {"to": "client@email.com", "subject": "...", "body_html": "...",
    #      "status": "pending|sent|cancelled"}
    output_actions: list[dict] = field(default_factory=list)
    # ex: [{"type": "create_devis", "label": "Créer devis PRO-XXX",
    #        "payload": {...}, "status": "pending|confirmed|cancelled", "comment": ""}]
    output_silent: list[dict] = field(default_factory=list)
    # ex: [{"type": "log_agenda", "label": "Log email agenda", "status": "done"}]

    # ── Contrôle pipeline ─────────────────────────────────────────────────
    skip_remaining: bool = False
    errors: list[dict] = field(default_factory=list)

    # ── Données arbitraires inter-steps ───────────────────────────────────
    extra: dict = field(default_factory=dict)

    def add_error(self, step: str, error: Exception | str) -> None:
        self.errors.append({"step": step, "error": str(error)})

    def to_summary(self) -> dict[str, Any]:
        """Résumé lisible pour les logs et les outputs JSON."""
        return {
            "email_id": self.email_id,
            "email_subject": self.email_subject,
            "socid": self.socid,
            "soc_nom": self.soc_nom,
            "nom_projet": self.nom_projet,
            "devis_id": self.devis_id,
            "devis_ref": self.devis_ref,
            "composants_count": len(self.composants_isoles),
            "routing_category": self.routing_category,
            "urgence": self.email_sentiment.get("urgence", ""),
            "errors": self.errors,
        }
