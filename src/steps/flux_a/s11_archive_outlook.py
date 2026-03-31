"""steps/flux_a/s11_archive_outlook.py — Archivage de l'email dans le dossier devis Outlook."""
import logging

from src import config
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context
from src.utils.pipeline_helpers import write_stage_output

logger = logging.getLogger(__name__)


async def s11_archive_outlook(ctx: Context) -> None:
    """
    Déplace l'email entrant dans le sous-dossier Outlook du devis.

    - Utilise ctx.outlook_folder_id si déjà créé par s08 (cas nominal).
    - Sinon crée/récupère le dossier sous OUTLOOK_FOLDER_DOSSIERS_DEVIS.
    - Fallback sur OUTLOOK_FOLDER_DEVIS si DOSSIERS_DEVIS non configuré.
    """
    outlook = OutlookClient()
    folder_name = f"{ctx.devis_ref} — {(ctx.soc_nom or '')[:180]}"

    # Résoudre le dossier cible
    folder_id = ctx.outlook_folder_id
    if not folder_id:
        parent = config.OUTLOOK_FOLDER_DOSSIERS_DEVIS or config.OUTLOOK_FOLDER_DEVIS
        folder_id = await outlook.get_or_create_folder(parent, folder_name)
        ctx.outlook_folder_id = folder_id

    await outlook.update_message_subject(
        ctx.email_id,
        f"[Traité] {ctx.email_subject}"
    )
    await outlook.move_message(ctx.email_id, folder_id)
    logger.info(f"Email archivé dans {folder_name!r}")

    # Archivage complet : effacer le marker anti-doublon pour laisser place au prochain email
    write_stage_output(4, {"email_id": None, "devis_id": None, "devis_ref": None})
