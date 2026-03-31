"""steps/flux_a/s09_upload_attachments.py — Upload des PJ dans le dossier Dolibarr."""
import logging

from src.connectors.dolibarr import DolibarrClient
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context
from src.utils.pipeline_helpers import upload_attachments_to_proposal

logger = logging.getLogger(__name__)


async def s09_upload_attachments(ctx: Context) -> None:
    """Upload les PJ de l'email dans le dossier du devis Dolibarr."""
    if not ctx.attachments or not ctx.devis_ref:
        return
    await upload_attachments_to_proposal(
        OutlookClient(), DolibarrClient(), ctx.email_id, ctx.devis_ref, ctx.attachments
    )
