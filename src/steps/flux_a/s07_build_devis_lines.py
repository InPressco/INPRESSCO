"""steps/flux_a/s07_build_devis_lines.py — Construction des lignes de devis Dolibarr."""
import logging

from src.middleware.context import Context
from src.utils.devis_builder import build_lines

logger = logging.getLogger(__name__)


async def s07_build_devis_lines(ctx: Context) -> None:
    """Construit les lignes Dolibarr depuis les composants analysés."""
    ctx.devis_lines = build_lines(ctx.composants_isoles, ctx.synthese_contexte)
    logger.info(f"{len(ctx.devis_lines)} ligne(s) de devis construite(s)")
