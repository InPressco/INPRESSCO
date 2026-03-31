"""steps/flux_a/s03_clean_data.py — Validation routing + nettoyage données client."""
import logging

from src import config
from src.middleware.context import Context
from src.middleware.pipeline import StopPipeline

logger = logging.getLogger(__name__)

# Catégories qui poursuivent le pipeline Flux A (nouveau devis)
_CATEGORIES_DEVIS = {"NEW_PROJECT"}


async def s03_clean_data(ctx: Context) -> None:
    """
    1. Valide la catégorie de routing (skill mail-routing-inpressco).
       → StopPipeline si l'email n'est pas un nouveau devis client.
    2. Nettoie les espaces, filtre les données InPressco résiduelles.
    """
    # ── Routing check ──────────────────────────────────────────────────────
    cat = ctx.routing_category or "UNKNOWN"
    if cat not in _CATEGORIES_DEVIS:
        motif = f"Email classifié '{cat}' (pas un nouveau devis) — pipeline arrêté proprement."
        logger.info(motif)
        raise StopPipeline(motif)

    # ── Nettoyage données client ───────────────────────────────────────────
    data = ctx.client_data
    for key, val in data.items():
        if isinstance(val, str):
            data[key] = val.strip()

    soc = data.get("soc_nom", "") or ""
    if any(excl.lower() in soc.lower() for excl in config.INPRESSCO_EXCLUDE_NAMES):
        logger.warning(f"soc_nom contient un nom InPressco : {soc!r} → mis à null")
        data["soc_nom"] = None

    ctx.client_data = data
