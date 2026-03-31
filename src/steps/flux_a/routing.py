"""steps/flux_a/routing.py — Helpers de routing Outlook post-s02 (catégories non-devis)."""
import logging

from src import config
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context

logger = logging.getLogger(__name__)


async def s_mark_non_devis(ctx: Context) -> None:
    """
    Marque l'email [Routé-{categorie}] sans déplacer.
    Utilisé uniquement pour PROJECT_UPDATE (géré par Flux B dans ETUDE).
    """
    outlook = OutlookClient()
    cat = ctx.routing_category or "UNKNOWN"
    new_subject = f"[Routé-{cat}] {ctx.email_subject}"
    try:
        await outlook.update_message_subject(ctx.email_id, new_subject)
        logger.info(f"Email marqué {new_subject!r} (PROJECT_UPDATE → Flux B)")
    except Exception as e:
        logger.warning(f"s_mark_non_devis : impossible de renommer le mail → {e}")


async def s_route_to_admin(ctx: Context) -> None:
    """
    Marque l'email [Routé-ADMIN] et le déplace vers le dossier ADMIN.
    Utilisé pour ADMINISTRATIF_GENERALE.
    """
    outlook = OutlookClient()
    cat = ctx.routing_category or "ADMINISTRATIF_GENERALE"
    new_subject = f"[Routé-{cat}] {ctx.email_subject}"
    try:
        await outlook.update_message_subject(ctx.email_id, new_subject)
        await outlook.move_message(ctx.email_id, config.OUTLOOK_FOLDER_ADMIN)
        logger.info(f"Email {new_subject!r} → dossier ADMIN")
    except Exception as e:
        logger.warning(f"s_route_to_admin : échec → {e}")


async def s_route_to_commerce(ctx: Context) -> None:
    """
    Marque l'email [Routé-{categorie}] et le déplace vers le dossier adapté.
    VISUAL_CREATION → MARKETING / RS
    PRICE_REQUEST / ACTION / UNKNOWN → COMMERCE
    """
    outlook = OutlookClient()
    cat = ctx.routing_category or "UNKNOWN"
    new_subject = f"[Routé-{cat}] {ctx.email_subject}"
    dest_folder = (
        config.OUTLOOK_FOLDER_MARKETING_RS
        if cat == "VISUAL_CREATION"
        else config.OUTLOOK_FOLDER_COMMERCE
    )
    dest_label = "MARKETING_RS" if cat == "VISUAL_CREATION" else "COMMERCE"
    try:
        await outlook.update_message_subject(ctx.email_id, new_subject)
        await outlook.move_message(ctx.email_id, dest_folder)
        logger.info(f"Email {new_subject!r} → dossier {dest_label}")
    except Exception as e:
        logger.warning(f"s_route_to_commerce : échec → {e}")
