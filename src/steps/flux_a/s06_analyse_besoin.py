"""steps/flux_a/s06_analyse_besoin.py — Analyse du besoin d'impression via Claude."""
import asyncio
import logging

from src.connectors.claude_client import ClaudeClient
from src.middleware.context import Context
from shared_lib.html_cleaner import prepare_email_for_ai
from shared_lib.imposition import post_process_composants

logger = logging.getLogger(__name__)


async def s06_analyse_besoin(ctx: Context) -> None:
    """Analyse le besoin d'impression via IA. Extrait les composants structurés."""
    await asyncio.sleep(13)  # anti-rate-limit : 5 req/min → 12s entre chaque appel
    ai = ClaudeClient()
    clean_body = prepare_email_for_ai(ctx.email_body)
    result = await ai.analyse_besoin_impression(clean_body)

    ctx.synthese_contexte = result.get("synthese_contexte", "")
    ctx.date_livraison_souhaitee = result.get("date_livraison_souhaitee")
    composants = result.get("composants_isoles", [])

    # Post-processing Python : imposition + score (plus fiable que le LLM)
    ctx.composants_isoles = post_process_composants(composants)
    logger.info(f"Analyse besoin : {len(ctx.composants_isoles)} composant(s) identifié(s)")
