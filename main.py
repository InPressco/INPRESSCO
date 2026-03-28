"""main.py — Pipeline InPressco : un seul flux entrant depuis la boîte de réception.

Architecture :
  Boîte de réception (contact@in-pressco.com)
      ↓
  s01  Récupère le dernier email non traité
  s02  Analyse Claude (extraction client + sentiment + routing) en parallèle
      ↓  routing_category
  NEW_PROJECT      → flux_a (s03→s12) : devis complet
  PROJECT_UPDATE   → déplacé vers >> ETUDE PROJET → déclenche N8N
  SUPPLIER_INVOICE → déplacé vers ADMIN           → déclenche N8N
  autres           → log uniquement, aucune action Python
"""
import asyncio
import logging
import sys

from src.middleware.context import Context
from src.middleware.pipeline import Pipeline, StopPipeline
from src.steps.flux_a.steps import s01_get_email, s02_extract_client_ai
from src.engine.dispatcher import route

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── Pipeline d'entrée (commun à tous les flux) ────────────────────────────────
intake = (
    Pipeline("intake")
    .add(s01_get_email)        # lit la boîte de réception
    .add(s02_extract_client_ai)  # analyse Claude : extraction + sentiment + routing
)


async def run_once() -> None:
    """Traite UN email depuis la boîte de réception."""
    logger.info("═" * 60)
    logger.info("InPressco Pipeline — démarrage")
    logger.info("═" * 60)

    # Étape 1 : lire l'email + analyser
    ctx = await intake.run(Context())

    if ctx.errors or ctx.skip_remaining:
        category = ctx.routing_category or "—"
        logger.info(f"Intake terminé (catégorie: {category!r}) — pas de pipeline secondaire")
        logger.info("═" * 60)
        logger.info("Pipeline terminé")
        logger.info("═" * 60)
        return

    # Étape 2 : router vers le bon pipeline
    pipeline = route(ctx)

    if pipeline is None:
        logger.info(
            f"Catégorie {ctx.routing_category!r} → aucun pipeline Python déclenché "
            "(géré par N8N ou ignoré)"
        )
    else:
        ctx = await pipeline.run(ctx)
        if ctx.errors:
            logger.error(f"Pipeline terminé avec erreurs : {ctx.errors}")
        elif ctx.devis_ref:
            logger.info(f"Pipeline OK — devis créé : {ctx.devis_ref}")
        else:
            logger.info("Pipeline terminé")

    logger.info("═" * 60)
    logger.info("Pipeline terminé")
    logger.info("═" * 60)


if __name__ == "__main__":
    asyncio.run(run_once())
