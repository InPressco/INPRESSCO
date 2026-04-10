"""steps/flux_a/s07_build_devis_lines.py — Construction des lignes de devis Dolibarr."""
import logging

from src.middleware.context import Context
from shared_lib.devis_builder import build_autonotes_private, build_lines

logger = logging.getLogger(__name__)


async def s07_build_devis_lines(ctx: Context) -> None:
    """Construit les lignes Dolibarr et les données techniques internes."""
    ctx.devis_lines = build_lines(ctx.composants_isoles, ctx.synthese_contexte)
    ctx.autonotes_private = build_autonotes_private(
        ctx.composants_isoles, run_id=ctx.email_id
    )
    logger.info(
        f"{len(ctx.devis_lines)} ligne(s) de devis construite(s) — "
        f"autonotes_private={bool(ctx.autonotes_private)}"
    )
