"""engine/main.py — Moteur central InPressco.

Boucle de polling : toutes les POLL_INTERVAL_SECONDS secondes,
tente de traiter un email depuis le dossier DEVIS (Flux A)
et les sous-dossiers ETUDE PROJET (Flux B), en parallèle.

Lancer avec :
    python -m src.engine.main
    python -m src.engine.main --dry-run   # simule sans écrire (TODO)
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# Assurer que la racine du projet est dans sys.path (pour imports src.*)
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src import config
from src.engine import dispatcher
from src.middleware.context import Context
from src.middleware.pipeline import Pipeline, StopPipeline
from src.steps.flux_a.steps import s01_get_email, s02_extract_client_ai
from src.steps.flux_b.steps import s01_get_subfolders, s02_get_messages, s03_process_messages

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("engine.main")


# ── Flux A — Nouveau email dans DEVIS ──────────────────────────────────────

async def run_flux_a() -> None:
    """
    Flux A : réception d'un email depuis le dossier DEVIS Outlook.

    1. s01 — récupère le 1er email non traité
    2. s02 — 3 appels Claude parallèles (extraction + sentiment + routing)
    3. dispatcher.route() — sélectionne le pipeline selon routing_category
    4. pipeline.run() — exécute les steps s03→s11
    """
    ctx = Context()

    # ── Gate : récupération + analyse IA ──────────────────────────────────
    gate = Pipeline("gate")
    gate.add(s01_get_email)
    gate.add(s02_extract_client_ai)
    ctx = await gate.run(ctx)

    if ctx.skip_remaining:
        # Pas d'email à traiter, ou erreur non bloquante → stop propre
        return

    # ── Dispatch → bon pipeline ────────────────────────────────────────────
    pipeline = dispatcher.route(ctx)
    if pipeline is None:
        logger.info(
            f"Flux A : email '{ctx.routing_category}' reçu de {ctx.email_sender_address!r} "
            "— aucun pipeline déclenché."
        )
        return

    await pipeline.run(ctx)

    if ctx.errors:
        logger.error(
            f"Flux A terminé avec erreurs sur devis {ctx.devis_ref!r} : {ctx.errors}"
        )
    else:
        logger.info(
            f"Flux A ✓ — devis {ctx.devis_ref!r} créé pour {ctx.soc_nom!r}"
        )


# ── Flux B — Emails dans les sous-dossiers ETUDE PROJET ──────────────────

async def run_flux_b() -> None:
    """
    Flux B : traitement des emails dans les sous-dossiers ETUDE PROJET.

    1. s01 — liste les sous-dossiers ETUDE
    2. s02 — récupère les emails non traités dans chaque sous-dossier
    3. s03 — upload PJ + log agenda + marque [Traité] pour chaque email
    """
    ctx = Context()
    pipeline = Pipeline("flux_b")
    pipeline.add(s01_get_subfolders)
    pipeline.add(s02_get_messages)
    pipeline.add(s03_process_messages)
    await pipeline.run(ctx)

    results = ctx.extra.get("flux_b_results", [])
    ok = sum(1 for r in results if r.get("status") == "ok")
    if ok:
        logger.info(f"Flux B ✓ — {ok} email(s) ETUDE traité(s)")


# ── Cycle de polling ────────────────────────────────────────────────────────

async def poll_once() -> None:
    """Exécute Flux A et Flux B en parallèle (une passe complète)."""
    logger.debug("Début passe de polling")
    results = await asyncio.gather(run_flux_a(), run_flux_b(), return_exceptions=True)
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            flux = "A" if i == 0 else "B"
            logger.error(f"Flux {flux} — exception non gérée : {res}", exc_info=res)


async def main() -> None:
    """Boucle principale de polling."""
    interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
    logger.info(f"Moteur InPressco démarré — polling toutes les {interval}s")

    while True:
        await poll_once()
        logger.debug(f"Passe terminée — attente {interval}s")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
