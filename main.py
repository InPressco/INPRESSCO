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
            # Tagger l'email [Erreur-{step}] pour éviter les boucles de retraitement
            if ctx.email_id:
                from src.connectors.outlook import OutlookClient
                failed_step = ctx.errors[0].get("step", "step") if ctx.errors else "step"
                new_subject = f"[Erreur-{failed_step}] {ctx.email_subject}"
                try:
                    await OutlookClient().update_message_subject(ctx.email_id, new_subject)
                    logger.info(f"Email tagué en erreur : {new_subject!r}")
                except Exception as tag_err:
                    logger.warning(f"Impossible de tagger l'email en erreur : {tag_err}")
        elif ctx.devis_ref:
            logger.info(f"Pipeline OK — devis créé : {ctx.devis_ref}")
        else:
            logger.info("Pipeline terminé")

    logger.info("═" * 60)
    logger.info("Pipeline terminé")
    logger.info("═" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="InPressco Pipeline — traitement emails + outils système",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python main.py                   # traite un email depuis la boîte de réception\n"
            "  python main.py --verify          # vérifie toutes les connexions + intégrité\n"
            "  python main.py --report          # génère SYSTEM_REPORT.md + .svg\n"
            "  python main.py --synthesis       # génère STRATEGIC_SYNTHESIS.md + .svg (live Dolibarr)\n"
            "  python main.py --check-dashboard # teste tous les endpoints dashboard + rapport\n"
        ),
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Vérification masquée : connexions API, pipeline, skills, anti-patterns",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Génère reports/SYSTEM_REPORT.md + SYSTEM_REPORT.svg",
    )
    parser.add_argument(
        "--synthesis",
        action="store_true",
        help="Génère reports/STRATEGIC_SYNTHESIS.md + .svg depuis Dolibarr live",
    )
    parser.add_argument(
        "--check-dashboard",
        action="store_true",
        dest="check_dashboard",
        help="Teste tous les endpoints dashboard + génère DASHBOARD_REPORT.md",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port du dashboard (défaut: 8080)",
    )
    parser.add_argument(
        "--start-if-down",
        action="store_true",
        dest="start_if_down",
        help="Démarre le dashboard si non disponible (avec --check-dashboard)",
    )
    args = parser.parse_args()

    if args.verify:
        from tools.system_verify import run_verify
        asyncio.run(run_verify())
    elif args.report:
        from tools.system_report_generator import generate_all
        asyncio.run(generate_all())
    elif args.synthesis:
        from tools.strategic_synthesis import run_synthesis
        asyncio.run(run_synthesis())
    elif args.check_dashboard:
        from tools.dashboard_verify import run_dashboard_verify, generate_dashboard_report_md
        base = f"http://127.0.0.1:{args.port}"
        report = asyncio.run(run_dashboard_verify(
            base=base,
            start_if_down=args.start_if_down,
        ))
        generate_dashboard_report_md(report)
        summary = report["summary"]
        ok  = summary["ok"]
        tot = ok + summary["warn"] + summary["error"] + summary.get("skip", 0)
        icon = "✅" if report["overall"] == "healthy" else "⚠️" if report["overall"] == "degraded" else "🔴"
        print(f"{icon} Dashboard {report['overall'].upper()} — {ok}/{tot} endpoints OK → reports/DASHBOARD_REPORT.md")
    else:
        asyncio.run(run_once())
