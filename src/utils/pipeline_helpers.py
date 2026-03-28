"""src/utils/pipeline_helpers.py — Helpers partagés entre Flux A et Flux B."""
import base64
import json
import logging
import os
from pathlib import Path

from src import config
from src.connectors.dolibarr import DolibarrClient
from src.connectors.outlook import OutlookClient

logger = logging.getLogger(__name__)

# Mapping numéro de stage → dossier output
_STAGE_DIRS = {
    1: "stages/01_extraction_email/output",
    2: "stages/02_analyse_client/output",
    3: "stages/03_analyse_besoin_impression/output",
    4: "stages/04_construction_devis/output",
    5: "stages/05_archivage/output",
}


def write_stage_output(stage: int, data: dict) -> None:
    """Écrit le résultat d'un stage dans stages/0N_*/output/result.json."""
    stage_dir = _STAGE_DIRS.get(stage)
    if not stage_dir:
        logger.warning(f"write_stage_output : stage {stage} inconnu")
        return
    os.makedirs(stage_dir, exist_ok=True)
    path = Path(stage_dir) / "result.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug(f"Stage {stage} output écrit → {path}")


def read_stage_output(stage: int) -> dict | None:
    """Lit le result.json d'un stage. Retourne None si absent ou invalide."""
    stage_dir = _STAGE_DIRS.get(stage)
    if not stage_dir:
        return None
    path = Path(stage_dir) / "result.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"read_stage_output stage {stage} : {e}")
        return None


async def upload_attachments_to_proposal(
    outlook: OutlookClient,
    doli: DolibarrClient,
    msg_id: str,
    devis_ref: str,
    attachments: list[dict],
) -> None:
    """Télécharge et uploade une liste de PJ dans un devis Dolibarr."""
    for att in attachments:
        filename = att.get("name", "piece_jointe")
        try:
            content = await outlook.download_attachment(msg_id, att["id"])
            b64 = base64.b64encode(content).decode("utf-8")
            await doli.upload_document(
                modulepart="proposal",
                ref=devis_ref,
                filename=f"PJ Mail - {filename}",
                b64content=b64,
            )
            logger.info(f"PJ uploadée : {filename!r} → devis {devis_ref!r}")
        except Exception as e:
            logger.error(f"Échec upload PJ {filename!r} → devis {devis_ref!r} : {e}")


async def log_email_to_agenda(
    doli: DolibarrClient,
    msg_id: str,
    sender_address: str,
    to_addresses: str,
    subject: str,
    body_preview: str,
    socid: int,
    devis_id: int,
    devis_ref: str = "",
) -> None:
    """Crée un événement agenda Dolibarr lié à un email et un devis."""
    if not devis_id:
        logger.warning(f"log_email_to_agenda ignoré : devis_id manquant (devis_ref={devis_ref!r})")
        return
    await doli.create_agenda_event({
        "type_code": "AC_OTH_AUTO",
        "userownerid": config.DOLIBARR_USER_OWNER_ID,
        "percentage": -1,
        "socid": socid,
        "code": "AC_MAILRECEIVED",
        "label": "Mail reçu",
        "email_msgid": msg_id,
        "email_from": sender_address,
        "email_to": to_addresses,
        "email_subject": subject,
        "note": body_preview,
        "elementtype": "propal",
        "fk_element": devis_id,
    })
    logger.info(f"Événement agenda créé{' pour devis ' + devis_ref if devis_ref else ''}")
