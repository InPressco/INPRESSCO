"""steps/flux_a/s10_log_email.py — Log de l'email dans l'agenda Dolibarr."""
import logging

from src.connectors.dolibarr import DolibarrClient
from src.middleware.context import Context
from src.utils.pipeline_helpers import log_email_to_agenda

logger = logging.getLogger(__name__)


async def s10_log_email(ctx: Context) -> None:
    """Crée un événement agenda dans Dolibarr lié au devis."""
    if not ctx.devis_id:
        logger.warning("Pas de devis_id, log agenda ignoré")
        return
    await log_email_to_agenda(
        DolibarrClient(),
        ctx.email_id,
        ctx.email_sender_address,
        ",".join(ctx.email_to_recipients),
        ctx.email_subject,
        ctx.email_body_preview,
        ctx.socid,
        ctx.devis_id,
        ctx.devis_ref,
    )
