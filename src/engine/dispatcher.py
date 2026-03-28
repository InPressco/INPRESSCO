"""engine/dispatcher.py — Routing email → chaîne de steps.

Après s01 (récupération email) + s02 (analyse Claude en parallèle),
`route()` construit le Pipeline approprié selon ctx.routing_category.

Catégories → chaîne :
  NEW_PROJECT      → flux_a  (s03→s11)
  PROJECT_UPDATE   → log uniquement (Flux B géré séparément via ETUDE dossiers)
  VISUAL_CREATION  → log uniquement (TODO : chaîne dédiée)
  SUPPLIER_INVOICE → log uniquement (TODO : chaîne admin)
  SUPPLIER_QUOTE   → log uniquement (TODO : chaîne admin)
  PRICE_REQUEST    → log uniquement
  ACTION           → log uniquement (email interne @inpressco.fr)
  UNKNOWN          → log uniquement
"""
import logging

from src.middleware.context import Context
from src.middleware.pipeline import Pipeline
from src.steps.flux_a.steps import (
    s03_clean_data,
    s04_find_or_create_client,
    s05_get_attachments,
    s06_analyse_besoin,
    s07_build_devis_lines,
    s08_create_devis,
    s09_upload_attachments,
    s10_log_email,
    s11_archive_outlook,
    s12_notify_team,
    s13_send_email_client,
)

logger = logging.getLogger(__name__)

# Catégories qui déclenchent la création d'un devis (Flux A complet)
_CATEGORIES_DEVIS = {"NEW_PROJECT"}

# Catégories gérées par Flux B (emails dans sous-dossiers ETUDE) — pas de pipeline ici
_CATEGORIES_FLUX_B = {"PROJECT_UPDATE"}


def build_flux_a() -> Pipeline:
    """Construit le Pipeline Flux A : s03→s12 (création devis + notification interne GO).
    L'envoi client (s13) est déclenché manuellement via le bouton GO dans l'email interne.
    """
    p = Pipeline("flux_a")
    p.add(s03_clean_data)
    p.add(s04_find_or_create_client)
    p.add(s05_get_attachments)
    p.add(s06_analyse_besoin)
    p.add(s07_build_devis_lines)
    p.add(s08_create_devis)
    p.add(s09_upload_attachments)
    p.add(s10_log_email)
    p.add(s11_archive_outlook)
    p.add(s12_notify_team)   # STOP — attend le GO humain avant d'envoyer au client
    return p


def route(ctx: Context) -> Pipeline | None:
    """
    Retourne le Pipeline à exécuter selon ctx.routing_category.
    Retourne None si l'email ne nécessite pas de pipeline (log + stop).
    """
    cat = ctx.routing_category or "UNKNOWN"

    if cat in _CATEGORIES_DEVIS:
        logger.info(f"Dispatch → flux_a (catégorie : {cat!r})")
        return build_flux_a()

    if cat in _CATEGORIES_FLUX_B:
        logger.info(
            f"Email catégorie {cat!r} → géré par Flux B (sous-dossiers ETUDE), "
            "pas de pipeline Flux A."
        )
        return None

    logger.info(
        f"Email catégorie {cat!r} → aucun pipeline déclenché. "
        f"Sujet : {ctx.email_subject!r}"
    )
    return None
