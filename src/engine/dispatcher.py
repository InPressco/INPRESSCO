"""engine/dispatcher.py — Routing email → chaîne de steps.

Après s01 (récupération email) + s02 (analyse Claude en parallèle),
`route()` construit le Pipeline approprié selon ctx.routing_category.

Catégories → chaîne :
  NEW_PROJECT           → flux_a  (s03→s12) : nouveau devis client  → ETUDE PROJET
  PROJECT_UPDATE        → mark [Routé-] sans déplacer (Flux B géré via sous-dossiers ETUDE)
  SUPPLIER_QUOTE        → flux_c  (sc01→sc07) : devis fournisseur   → DEVIS_FOURNISSEUR
  SUPPLIER_INVOICE      → flux_c  (sc01→sc07) : facture fournisseur → FACTURE_FOURNISSEUR
  ADMINISTRATIF_GENERALE→ mark [Routé-] + move ADMIN
  VISUAL_CREATION       → mark [Routé-] + move COMMERCE
  PRICE_REQUEST         → mark [Routé-] + move COMMERCE
  ACTION                → mark [Routé-] + move COMMERCE (email interne @inpressco.fr)
  UNKNOWN               → mark [Routé-] + move COMMERCE
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
    s_mark_non_devis,
    s_route_to_admin,
    s_route_to_commerce,
)
from src.steps.flux_c.steps import (
    sc01_identify_supplier,
    sc02_get_attachments,
    sc03_extract_linked_ref,
    sc04_log_agenda,
    sc05_upload_attachments,
    sc06_notify_team,
    sc07_archive_outlook,
)

logger = logging.getLogger(__name__)

# Catégories qui déclenchent la création d'un devis (Flux A complet)
_CATEGORIES_DEVIS = {"NEW_PROJECT"}

# Catégories gérées par Flux B (emails dans sous-dossiers ETUDE) — juste marquage
_CATEGORIES_FLUX_B = {"PROJECT_UPDATE"}

# Catégories fournisseurs traitées par Flux C
_CATEGORIES_FOURNISSEUR = {"SUPPLIER_QUOTE", "SUPPLIER_INVOICE"}

# Administratif → déplacer vers ADMIN
_CATEGORIES_ADMIN = {"ADMINISTRATIF_GENERALE"}

# Tout le reste (commerce) → déplacer vers COMMERCE
# VISUAL_CREATION, PRICE_REQUEST, ACTION, UNKNOWN


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


def build_flux_c() -> Pipeline:
    """Construit le Pipeline Flux C : traitement des emails fournisseurs (sc01→sc07)."""
    p = Pipeline("flux_c")
    p.add(sc01_identify_supplier)
    p.add(sc02_get_attachments)
    p.add(sc03_extract_linked_ref)
    p.add(sc04_log_agenda)
    p.add(sc05_upload_attachments)
    p.add(sc06_notify_team)
    p.add(sc07_archive_outlook)
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
            f"marquage [Routé-{cat}] sans déplacement."
        )
        return Pipeline("mark_project_update").add(s_mark_non_devis)

    if cat in _CATEGORIES_FOURNISSEUR:
        logger.info(f"Dispatch → flux_c (catégorie : {cat!r})")
        return build_flux_c()

    if cat in _CATEGORIES_ADMIN:
        logger.info(f"Dispatch → ADMIN (catégorie : {cat!r})")
        return Pipeline("route_to_admin").add(s_route_to_admin)

    # Tout le reste (VISUAL_CREATION, PRICE_REQUEST, ACTION, UNKNOWN) → COMMERCE
    logger.info(
        f"Email catégorie {cat!r} → COMMERCE. Sujet : {ctx.email_subject!r}"
    )
    return Pipeline("route_to_commerce").add(s_route_to_commerce)
