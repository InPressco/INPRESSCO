"""steps/flux_b/steps.py — Steps du Flux B : Suivi de devis existants."""
import asyncio
import logging

from src import config
from src.connectors.dolibarr import DolibarrClient
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context
from src.middleware.pipeline import StopPipeline
from src.utils.pipeline_helpers import log_email_to_agenda, upload_attachments_to_proposal

logger = logging.getLogger(__name__)


# ── Step 1 — Récupération sous-dossiers ETUDE ────────────────────────────

async def s01_get_subfolders(ctx: Context) -> None:
    """Récupère les sous-dossiers du dossier >> ETUDE PROJET."""
    outlook = OutlookClient()
    folder_id = config.OUTLOOK_FOLDER_ETUDE
    try:
        folders = await outlook.get_folders(folder_id)
    except Exception:
        logger.warning("s01 Flux B : ID dossier ETUDE invalide, résolution par nom...")
        folder_id = await outlook.get_folder_id_by_name("ETUDE PROJET")
        if not folder_id:
            raise StopPipeline("Dossier ETUDE PROJET introuvable dans Outlook")
        logger.info(f"s01 Flux B : dossier ETUDE résolu → {folder_id}")
        folders = await outlook.get_folders(folder_id)
    ctx.extra["etude_folders"] = {f["id"]: f["displayName"] for f in folders}
    logger.info(f"{len(folders)} sous-dossier(s) ETUDE trouvé(s)")


# ── Step 2 — Récupération emails dans les sous-dossiers ──────────────────

async def s02_get_messages(ctx: Context) -> None:
    """Récupère tous les emails non traités dans les sous-dossiers ETUDE."""
    folders = ctx.extra.get("etude_folders", {})
    if not folders:
        raise StopPipeline("Aucun sous-dossier ETUDE trouvé")

    folder_conditions = " or ".join(
        f"parentFolderId eq '{fid}'" for fid in folders
    )
    odata_filter = f"not(startswith(subject,'[Traité]')) and ({folder_conditions})"

    outlook = OutlookClient()
    messages = await outlook.get_messages(odata_filter=odata_filter, top=10)

    if not messages:
        raise StopPipeline("Aucun email non traité dans les sous-dossiers ETUDE")

    ctx.extra["etude_messages"] = messages
    logger.info(f"{len(messages)} email(s) à traiter dans les sous-dossiers ETUDE")


# ── Step 3 — Traitement de chaque message ────────────────────────────────

async def _process_one_message(
    msg: dict,
    folders: dict,
    doli: DolibarrClient,
    outlook: OutlookClient,
) -> dict:
    """Traite un email ETUDE : upload PJ, log agenda, marque [Traité]."""
    msg_id = msg["id"]
    subject = msg.get("subject", "")
    folder_name = folders.get(msg.get("parentFolderId", ""), "")

    ref, _ = _parse_folder_name(folder_name)
    if not ref:
        logger.warning(f"Ref introuvable dans le dossier : {folder_name!r}")
        return {"msg_id": msg_id, "status": "skipped", "reason": "ref introuvable"}

    try:
        devis = await doli.get_proposal_by_ref(ref)
    except Exception as e:
        logger.error(f"Devis {ref!r} non trouvé dans Dolibarr : {e}")
        return {"msg_id": msg_id, "status": "error", "reason": str(e)}

    devis_id = devis["id"]
    devis_ref = devis["ref"]
    socid = devis["socid"]

    # Upload PJ si présentes
    if msg.get("hasAttachments"):
        all_att = await outlook.get_attachments(msg_id)
        att_non_inline = [a for a in all_att if not a.get("isInline", True)]
        await upload_attachments_to_proposal(outlook, doli, msg_id, devis_ref, att_non_inline)

    # Log agenda
    sender_addr = msg.get("sender", {}).get("emailAddress", {}).get("address", "")
    to_addrs = ",".join(
        r["emailAddress"]["address"] for r in msg.get("toRecipients", [])
    )
    await log_email_to_agenda(
        doli, msg_id, sender_addr, to_addrs,
        subject, msg.get("bodyPreview", ""),
        socid, devis_id, devis_ref,
    )

    # Marquer [Traité]
    await outlook.update_message_subject(msg_id, f"[Traité] {subject}")
    logger.info(f"Email traité : {subject!r} → devis {devis_ref!r}")
    return {"msg_id": msg_id, "status": "ok", "devis_ref": devis_ref}


async def s03_process_messages(ctx: Context) -> None:
    """
    Pour chaque email dans les sous-dossiers ETUDE :
    - Extrait la ref et le client depuis le nom du dossier (format: "{ref} - {client}")
    - Récupère le devis Dolibarr correspondant
    - Upload les PJ, log l'agenda, marque [Traité]
    Traitement parallèle de tous les messages.
    """
    messages = ctx.extra.get("etude_messages", [])
    folders = ctx.extra.get("etude_folders", {})
    doli = DolibarrClient()
    outlook = OutlookClient()

    results = await asyncio.gather(*[
        _process_one_message(msg, folders, doli, outlook)
        for msg in messages
    ])
    ctx.extra["flux_b_results"] = list(results)


def _parse_folder_name(folder_name: str) -> tuple[str | None, str | None]:
    """
    Parse le nom du dossier Outlook au format "{ref} - {client}".
    Retourne (ref, client) ou (None, None) si non parseable.
    """
    if not folder_name or " - " not in folder_name:
        return None, None
    parts = folder_name.split(" - ", 1)
    return parts[0].strip(), parts[1].strip()
