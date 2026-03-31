"""steps/flux_c/steps.py — Flux C : traitement des emails fournisseurs.

Catégories traitées :
  SUPPLIER_QUOTE   → devis reçu d'un sous-traitant (réponse à une demande de prix)
  SUPPLIER_INVOICE → facture reçue d'un fournisseur

Pipeline :
  sc01_identify_supplier   → trouver le fournisseur dans Dolibarr (lecture seule)
  sc02_get_attachments     → récupérer les PJ de l'email (devis/facture PDF)
  sc03_extract_linked_ref  → chercher une ref devis InPressco dans le sujet/corps
  sc04_log_agenda          → créer un événement agenda Dolibarr
  sc05_upload_attachments  → uploader la PJ sur le devis lié (si ref trouvée)
  sc06_notify_team         → email interne d'alerte Nicolas/Paola
  sc07_archive_outlook     → marquer [Traité-FOURNISSEUR] + déplacer vers ADMIN
"""
import logging
import re

from src import config
from src.connectors.dolibarr import DolibarrClient
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context
from src.utils.pipeline_helpers import log_email_to_agenda, upload_attachments_to_proposal

logger = logging.getLogger(__name__)

# Regex pour extraire une référence InPressco depuis le sujet ou corps de l'email
# Capture : PRO-2026-0001, DEV-0001, CMD-2026-001, FA-001, etc.
_REF_PATTERN = re.compile(r'\b([A-Z]{2,5}[-_]?\d{4}(?:[-_]\d+)*)\b')


# ── sc01 — Identifier le fournisseur dans Dolibarr ────────────────────────

async def sc01_identify_supplier(ctx: Context) -> None:
    """Recherche le fournisseur dans Dolibarr par email expéditeur.
    Lecture seule : ne crée jamais un fournisseur automatiquement.
    """
    doli = DolibarrClient()
    found = await doli.find_thirdparty(
        email=ctx.email_sender_address,
        name=ctx.email_sender,
    )
    if found:
        ctx.supplier_socid = int(found["id"])
        ctx.supplier_nom = found.get("name", ctx.email_sender)
        logger.info(
            f"sc01 : fournisseur trouvé → socid={ctx.supplier_socid}, "
            f"nom={ctx.supplier_nom!r}"
        )
    else:
        ctx.supplier_nom = ctx.email_sender or ctx.email_sender_address
        logger.warning(
            f"sc01 : fournisseur non trouvé dans Dolibarr pour "
            f"{ctx.email_sender_address!r} — traitement sans socid"
        )


# ── sc02 — Récupérer les pièces jointes ───────────────────────────────────

async def sc02_get_attachments(ctx: Context) -> None:
    """Récupère les PJ non-inline de l'email fournisseur."""
    if not ctx.has_attachments:
        logger.info("sc02 : pas de pièces jointes.")
        return
    outlook = OutlookClient()
    all_att = await outlook.get_attachments(ctx.email_id)
    ctx.attachments = [a for a in all_att if not a.get("isInline", True)]
    logger.info(f"sc02 : {len(ctx.attachments)} pièce(s) jointe(s) récupérée(s)")


# ── sc03 — Extraire la ref devis InPressco depuis le sujet/corps ──────────

async def sc03_extract_linked_ref(ctx: Context) -> None:
    """Tente de trouver une référence de devis InPressco (ex: PRO-2026-0001)
    dans le sujet ou le début du corps de l'email.
    Si trouvée, charge le devis correspondant depuis Dolibarr.
    """
    search_text = ctx.email_subject + " " + ctx.email_body_preview
    matches = _REF_PATTERN.findall(search_text)
    if not matches:
        logger.info("sc03 : aucune référence InPressco détectée dans le sujet/corps")
        return

    doli = DolibarrClient()
    for ref in matches:
        try:
            proposal = await doli.get_proposal_by_ref(ref)
            ctx.linked_proposal_ref = proposal.get("ref", ref)
            ctx.linked_proposal_id = int(proposal["id"])
            logger.info(
                f"sc03 : référence trouvée → {ctx.linked_proposal_ref!r} "
                f"(id={ctx.linked_proposal_id})"
            )
            return
        except Exception:
            logger.debug(f"sc03 : ref {ref!r} non trouvée dans Dolibarr (essai suivant)")

    logger.info(f"sc03 : refs détectées {matches} — aucune ne correspond à un devis Dolibarr")


# ── sc04 — Log dans l'agenda Dolibarr ─────────────────────────────────────

async def sc04_log_agenda(ctx: Context) -> None:
    """Crée un événement agenda Dolibarr pour tracer la réception du document.
    Lié au devis InPressco si trouvé, sinon lié au tiers fournisseur seul.
    """
    cat = ctx.routing_category or "SUPPLIER_QUOTE"
    label_type = "Devis" if cat == "SUPPLIER_QUOTE" else "Facture"

    doli = DolibarrClient()
    await log_email_to_agenda(
        doli,
        ctx.email_id,
        ctx.email_sender_address,
        ",".join(ctx.email_to_recipients),
        f"[{label_type} fournisseur] {ctx.email_subject}",
        ctx.email_body_preview,
        ctx.supplier_socid,
        ctx.linked_proposal_id,
        ctx.linked_proposal_ref or "",
    )
    logger.info(
        f"sc04 : agenda loggé — fournisseur={ctx.supplier_nom!r}, "
        f"devis lié={ctx.linked_proposal_ref or 'aucun'!r}"
    )


# ── sc05 — Upload pièces jointes sur le devis lié ─────────────────────────

async def sc05_upload_attachments(ctx: Context) -> None:
    """Upload les PJ (devis/facture PDF) sur le devis Dolibarr lié.
    Ne fait rien si aucune PJ ou aucune référence devis InPressco trouvée.
    """
    if not ctx.attachments:
        return
    if not ctx.linked_proposal_ref:
        logger.info(
            "sc05 : PJ présente(s) mais aucun devis InPressco lié — "
            "upload ignoré (visible dans l'agenda Dolibarr)"
        )
        return
    await upload_attachments_to_proposal(
        OutlookClient(),
        DolibarrClient(),
        ctx.email_id,
        ctx.linked_proposal_ref,
        ctx.attachments,
    )
    logger.info(
        f"sc05 : {len(ctx.attachments)} PJ uploadée(s) → devis {ctx.linked_proposal_ref!r}"
    )


# ── sc06 — Notification interne ────────────────────────────────────────────

async def sc06_notify_team(ctx: Context) -> None:
    """Envoie un email interne résumant le document fournisseur reçu."""
    cat = ctx.routing_category or "SUPPLIER_QUOTE"
    label_type = "Devis" if cat == "SUPPLIER_QUOTE" else "Facture"
    emoji = "📥" if cat == "SUPPLIER_QUOTE" else "🧾"

    doli_web = config.DOLIBARR_BASE_URL.removesuffix("/api/index.php").removesuffix("/api")

    # Ligne devis lié
    devis_html = ""
    if ctx.linked_proposal_ref and ctx.linked_proposal_id:
        devis_link = f"{doli_web}/comm/propal/card.php?id={ctx.linked_proposal_id}"
        devis_html = f"""
        <tr>
          <td style="padding:6px 0;color:#6b7280;width:140px">Devis lié</td>
          <td style="padding:6px 0;font-weight:bold">
            <a href="{devis_link}" style="color:#1d4ed8">{ctx.linked_proposal_ref}</a>
          </td>
        </tr>"""

    # Lien fiche fournisseur
    fournisseur_html = ""
    if ctx.supplier_socid:
        fournisseur_link = f"{doli_web}/societe/card.php?socid={ctx.supplier_socid}"
        fournisseur_html = f"""
        <tr>
          <td style="padding:6px 0;color:#6b7280">Fiche Dolibarr</td>
          <td style="padding:6px 0">
            <a href="{fournisseur_link}" style="color:#1d4ed8">Voir le tiers</a>
          </td>
        </tr>"""

    # Liste PJ
    pj_html = ""
    if ctx.attachments:
        items = "".join(
            f"<li>{a.get('name', 'fichier')}</li>"
            for a in ctx.attachments
        )
        pj_html = f"<p style='font-weight:bold;margin:16px 0 6px'>Pièces jointes :</p><ul style='margin:0;padding-left:20px'>{items}</ul>"
    else:
        pj_html = "<p style='color:#9ca3af;font-style:italic'>Aucune pièce jointe</p>"

    body_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#1a1a2e;padding:16px 24px;border-radius:8px 8px 0 0">
        <h2 style="color:#f59e0b;margin:0">{emoji} {label_type} fournisseur reçu</h2>
        <p style="color:#d1d5db;margin:4px 0 0">{ctx.supplier_nom}</p>
      </div>
      <div style="background:#f8f9fa;padding:20px 24px;border:1px solid #e5e7eb">
        <table style="width:100%;border-collapse:collapse;margin-bottom:8px">
          <tr>
            <td style="padding:6px 0;color:#6b7280;width:140px">Fournisseur</td>
            <td style="padding:6px 0;font-weight:bold">{ctx.supplier_nom}</td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:#6b7280">Email</td>
            <td style="padding:6px 0">{ctx.email_sender_address}</td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:#6b7280">Objet</td>
            <td style="padding:6px 0">{ctx.email_subject}</td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:#6b7280">Type</td>
            <td style="padding:6px 0">{label_type}</td>
          </tr>
          {devis_html}
          {fournisseur_html}
        </table>
        {pj_html}
        <p style="color:#6b7280;font-size:12px;margin-top:20px">
          Email archivé dans Outlook — événement loggé dans l'agenda Dolibarr.
        </p>
      </div>
    </div>
    """

    try:
        outlook = OutlookClient()
        await outlook.send_email(
            to_email=config.INPRESSCO_INTERNAL_EMAIL,
            subject=f"[{label_type} fournisseur] {ctx.supplier_nom} — {ctx.email_subject[:60]}",
            body_html=body_html,
        )
        logger.info(f"sc06 : notification interne envoyée → {config.INPRESSCO_INTERNAL_EMAIL}")
    except Exception as e:
        logger.error(f"sc06 : échec envoi notification → {e}")
        ctx.add_error("sc06_notify", str(e))


# ── sc07 — Archivage Outlook ───────────────────────────────────────────────

async def sc07_archive_outlook(ctx: Context) -> None:
    """Marque l'email [Traité-FOURNISSEUR] et le déplace vers le dossier adapté.

    SUPPLIER_QUOTE   → OUTLOOK_FOLDER_DEVIS_FOURNISSEUR  (par défaut ADMIN)
    SUPPLIER_INVOICE → OUTLOOK_FOLDER_FACTURE_FOURNISSEUR (par défaut ADMIN)
    """
    outlook = OutlookClient()
    cat = ctx.routing_category or "SUPPLIER_QUOTE"
    new_subject = f"[Traité-FOURNISSEUR] {ctx.email_subject}"

    if cat == "SUPPLIER_INVOICE":
        dest_folder = config.OUTLOOK_FOLDER_FACTURE_FOURNISSEUR
        dest_label = "FACTURE_FOURNISSEUR"
    else:
        dest_folder = config.OUTLOOK_FOLDER_DEVIS_FOURNISSEUR
        dest_label = "DEVIS_FOURNISSEUR"

    try:
        await outlook.update_message_subject(ctx.email_id, new_subject)
        await outlook.move_message(ctx.email_id, dest_folder)
        logger.info(
            f"sc07 : email archivé → dossier {dest_label} ({ctx.supplier_nom!r})"
        )
    except Exception as e:
        logger.warning(f"sc07 : archivage Outlook échoué → {e}")
        ctx.add_error("sc07_archive", str(e))
