"""steps/flux_a/s05_get_attachments.py — Récupération des pièces jointes."""
import logging

from src.connectors.outlook import OutlookClient
from src.middleware.context import Context

logger = logging.getLogger(__name__)


async def s05_get_attachments(ctx: Context) -> None:
    """Récupère les pièces jointes non-inline de l'email."""
    if not ctx.has_attachments:
        logger.info("Pas de pièces jointes.")
        return

    outlook = OutlookClient()
    all_attachments = await outlook.get_attachments(ctx.email_id)
    ctx.attachments = [a for a in all_attachments if not a.get("isInline", True)]
    logger.info(f"{len(ctx.attachments)} pièce(s) jointe(s) non-inline récupérée(s)")
