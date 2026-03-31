"""steps/flux_a/s08_create_devis.py — Création du devis dans Dolibarr."""
import logging
from datetime import datetime, timezone

from src import config
from src.connectors.dolibarr import DolibarrClient
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context
from src.utils.pipeline_helpers import write_stage_output

logger = logging.getLogger(__name__)


async def s08_create_devis(ctx: Context) -> None:
    """Crée le devis dans Dolibarr, le valide pour générer la ref, puis remet en brouillon."""
    doli = DolibarrClient()

    # Conversion date email → epoch (une seule fois)
    received_str = ctx.email_received_at or datetime.now(timezone.utc).isoformat()
    received_dt = datetime.fromisoformat(received_str.replace("Z", "+00:00"))
    date_epoch = int(received_dt.timestamp())

    # Conversion date livraison souhaitée → epoch
    date_livraison = 0
    if ctx.date_livraison_souhaitee:
        try:
            date_livraison = int(datetime.fromisoformat(ctx.date_livraison_souhaitee).timestamp())
        except ValueError:
            logger.warning(f"Date livraison invalide : {ctx.date_livraison_souhaitee!r}")

    note_private = (
        f"Devis créé automatiquement par le pipeline Python, "
        f"à partir du mail \"{ctx.email_subject}\" reçu le "
        f"{received_dt.strftime('%d/%m/%Y')}"
    )

    payload = {
        "socid": ctx.socid,
        "date": date_epoch,
        "model_pdf": config.DOLIBARR_MODEL_PDF,
        "note_private": note_private,
        "date_livraison": date_livraison,
        "cond_reglement_id": config.DOLIBARR_COND_REGLEMENT_BAT,
        "mode_reglement_id": config.DOLIBARR_MODE_REGLEMENT_VIREMENT,
        "array_options": {
            "options_fhp_project_name": ctx.nom_projet
        },
        "lines": ctx.devis_lines,
    }

    # 1. Créer le devis
    created = await doli.create_proposal(payload)
    devis_id = int(created["id"])

    # Marker anti-doublon : écrire dès maintenant pour protéger contre un crash
    # entre la création du devis et l'archivage Outlook (s11).
    write_stage_output(4, {
        "email_id": ctx.email_id,
        "devis_id": devis_id,
        "devis_ref": "",  # sera mis à jour après validate
        "socid": ctx.socid,
        "soc_nom": ctx.soc_nom,
    })

    # 2. Valider → génère la référence PRO...
    validated = await doli.validate_proposal(devis_id)
    ctx.devis_ref = validated.get("ref", "")
    ctx.devis_id = devis_id

    # Mettre à jour le marker avec la ref définitive
    write_stage_output(4, {
        "email_id": ctx.email_id,
        "devis_id": devis_id,
        "devis_ref": ctx.devis_ref,
        "socid": ctx.socid,
        "soc_nom": ctx.soc_nom,
    })

    # 3. Remettre en brouillon pour édition manuelle
    await doli.set_to_draft(devis_id)

    # 4. Créer le dossier Outlook dédié à ce devis
    if config.OUTLOOK_FOLDER_DOSSIERS_DEVIS:
        try:
            outlook = OutlookClient()
            folder_display = f"{ctx.devis_ref} — {(ctx.soc_nom or '')[:100]}"
            folder_id = await outlook.get_or_create_folder(
                config.OUTLOOK_FOLDER_DOSSIERS_DEVIS,
                folder_display,
            )
            ctx.outlook_folder_id = folder_id
            logger.info(f"s08 : dossier Outlook créé → {folder_display!r}")
        except Exception as e:
            logger.warning(f"s08 : création dossier Outlook échouée → {e}")

    logger.info(f"Devis créé : id={ctx.devis_id}, ref={ctx.devis_ref!r}")
