"""steps/flux_a/s02_extract_client_ai.py — Extraction client + sentiment + routing via Claude."""
import asyncio
import logging

from src import config
from src.connectors.claude_client import ClaudeClient
from src.middleware.context import Context
from src.utils.html_cleaner import prepare_email_for_ai

logger = logging.getLogger(__name__)


async def s02_extract_client_ai(ctx: Context) -> None:
    """
    3 appels Claude séquentiels avec délai anti-rate-limit :
    1. extract_client_data   → ctx.client_data  (Opus — extraction complexe)
    2. analyse_sentiment     → ctx.email_sentiment (Haiku — classification)
    3. classify_routing      → ctx.routing_category (Haiku — classification)

    Séquentiel pour éviter le 429 rate_limit_error (limite 10k tokens/min).
    Délai de 13s entre chaque appel pour espacer la consommation.
    """
    ai = ClaudeClient()
    sender_info = f"{ctx.email_sender} <{ctx.email_sender_address}>"
    clean_body = prepare_email_for_ai(ctx.email_body)
    # Corps tronqué pour les appels Haiku (sentiment + routing) — 600 chars suffisent,
    # réduit ~3x la consommation de tokens sur ces appels secondaires.
    short_body = clean_body[:600] + ("…" if len(clean_body) > 600 else "")

    client_result: dict = {}
    sentiment_result: dict = {}
    routing_result: dict = {}

    try:
        client_result = await asyncio.wait_for(
            ai.extract_client_data(sender_info, clean_body), timeout=30.0
        )
    except asyncio.TimeoutError:
        logger.error("s02 : timeout extract_client_data")
        ctx.add_error("s02", "timeout extract_client_data")
    except Exception as e:
        logger.error(f"s02 extract_client_data échouée : {e}")

    await asyncio.sleep(13)

    try:
        sentiment_result = await asyncio.wait_for(
            ai.analyse_sentiment_email(sender_info, short_body), timeout=20.0
        )
    except asyncio.TimeoutError:
        logger.warning("s02 : timeout analyse_sentiment")
    except Exception as e:
        logger.warning(f"s02 analyse_sentiment échouée : {e}")

    await asyncio.sleep(13)

    try:
        routing_result = await asyncio.wait_for(
            ai.classify_email_routing(sender_info, short_body), timeout=20.0
        )
    except asyncio.TimeoutError:
        logger.warning("s02 : timeout classify_routing")
        ctx.add_error("s02", "timeout classify_routing")
        ctx.skip_remaining = True
        return
    except Exception as e:
        logger.warning(f"s02 classify_routing échouée : {e}")

    # ── Extraction client ──────────────────────────────────────────────────
    if isinstance(client_result, Exception):
        logger.error(f"s02 extraction client échouée : {client_result}")
        client_result = {}
    if client_result.get("email") and any(
        excl in client_result["email"] for excl in config.INPRESSCO_EXCLUDE_EMAILS
    ):
        client_result["email"] = None
    client_result["creation_si_non_trouve"] = False
    ctx.client_data = client_result
    ctx.nom_projet = client_result.get("nom_projet", "")
    logger.info(f"Client extrait : soc_nom={client_result.get('soc_nom')!r}, email={client_result.get('email')!r}")

    # ── Sentiment ──────────────────────────────────────────────────────────
    if isinstance(sentiment_result, Exception):
        logger.warning(f"s02 analyse sentiment échouée : {sentiment_result}")
        sentiment_result = {}
    ctx.email_sentiment = sentiment_result
    urgence = sentiment_result.get("urgence", "?")
    profil = sentiment_result.get("profil", "?")
    logger.info(f"Sentiment : urgence={urgence!r}, profil={profil!r}")

    # ── Routing ────────────────────────────────────────────────────────────
    if isinstance(routing_result, Exception):
        logger.warning(f"s02 routing classification échouée : {routing_result}")
        routing_result = {}
    ctx.routing_category = routing_result.get("categorie", "UNKNOWN")
    logger.info(f"Routing : categorie={ctx.routing_category!r}, confidence={routing_result.get('confidence')!r}")
