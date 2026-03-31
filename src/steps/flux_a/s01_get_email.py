"""steps/flux_a/s01_get_email.py — Récupération email depuis la drop zone FLUX_INPRESSCO."""
import logging

from src import config
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context
from src.middleware.pipeline import StopPipeline
from src.utils.pipeline_helpers import read_stage_output

logger = logging.getLogger(__name__)

# Exclure les emails déjà traités ([Traité]) ET déjà routés ([Routé-])
_ODATA_FILTER = (
    "not(startswith(subject,'[Traité]'))"
    " and not(startswith(subject,'[Routé-'))"
    " and not(startswith(subject,'[Erreur-'))"
)


async def s01_get_email(ctx: Context) -> None:
    """Récupère le dernier email non traité depuis la drop zone FLUX_INPRESSCO.

    FLUX_INPRESSCO est le point d'entrée universel du pipeline :
    - Règle Outlook : tous les emails entrants y sont routés automatiquement
    - Glisser-déposer manuel : tout email ou document à traiter
    Après traitement, chaque email est déplacé vers sa destination finale par le flux concerné.
    """
    outlook = OutlookClient()
    folder_id = config.OUTLOOK_FOLDER_PENDING
    try:
        emails = await outlook.get_emails(
            folder_id=folder_id,
            odata_filter=_ODATA_FILTER,
            top=1,
        )
    except Exception:
        # ID en config périmé → résoudre par nom
        logger.warning("s01 : ID dossier FLUX_INPRESSCO invalide, résolution par nom...")
        folder_id = await outlook.get_folder_id_by_name("FLUX INPRESSCO")
        if not folder_id:
            raise StopPipeline("Dossier FLUX INPRESSCO (drop zone) introuvable dans Outlook")
        logger.info(f"s01 : dossier FLUX_INPRESSCO résolu → {folder_id}")
        emails = await outlook.get_emails(
            folder_id=folder_id,
            odata_filter=_ODATA_FILTER,
            top=1,
        )
    if not emails:
        logger.info("Aucun email à traiter dans DEVIS.")
        raise StopPipeline("Pas d'email non traité")

    email = emails[0]
    ctx.email_id = email["id"]
    ctx.email_subject = email.get("subject", "")
    ctx.email_sender = email.get("sender", {}).get("emailAddress", {}).get("name", "")
    ctx.email_sender_address = email.get("sender", {}).get("emailAddress", {}).get("address", "")
    ctx.email_received_at = email.get("receivedDateTime", "")
    ctx.email_body = email.get("body", {}).get("content", "")
    ctx.email_body_preview = email.get("bodyPreview", "")
    ctx.has_attachments = email.get("hasAttachments", False)
    ctx.email_to_recipients = [
        r["emailAddress"]["address"]
        for r in email.get("toRecipients", [])
    ]
    logger.info(f"Email récupéré : {ctx.email_subject!r} de {ctx.email_sender_address}")

    # Vérification anti-doublon : si un devis a déjà été créé pour cet email
    # (pipeline planté entre s08 et s11), arrêter proprement plutôt que de créer un doublon.
    marker = read_stage_output(4)
    if marker and marker.get("email_id") == ctx.email_id and marker.get("devis_id"):
        motif = (
            f"Email déjà traité (devis {marker['devis_ref']!r} existant, "
            f"archivage Outlook incomplet). Nettoyage manuel requis."
        )
        logger.warning(motif)
        raise StopPipeline(motif)
