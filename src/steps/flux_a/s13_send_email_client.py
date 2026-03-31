"""steps/flux_a/s13_send_email_client.py — Envoi de l'email de réponse CONFIG_CLIENT_v2026."""
import asyncio
import logging

from src import config
from src.connectors.claude_client import ClaudeClient
from src.connectors.dolibarr import DolibarrClient
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context

logger = logging.getLogger(__name__)


async def s13_send_email_client(ctx: Context) -> None:
    """
    Génère et envoie l'email de réponse CONFIG_CLIENT_v2026 au client.

    - Génère le corps HTML via Claude (format 8 blocs InPressco)
    - Envoie via Microsoft Graph (sendMail) en réponse à l'email source
    - Log une note interne sur le devis Dolibarr
    - Stocke l'email généré dans ctx.email_reponse_client et ctx.output_response

    Préconditions :
    - ctx.email_sender_address doit être renseigné (destinataire réponse)
    - ctx.devis_ref doit être renseigné (référence du devis créé)
    - ctx.devis_id doit être renseigné (pour log agenda)
    """
    if not ctx.email_sender_address:
        logger.warning("s13 : email_sender_address vide — réponse client ignorée")
        return
    if not ctx.devis_ref:
        logger.warning("s13 : devis_ref vide — réponse client ignorée")
        return

    # ── Construire l'URL du devis uniquement si le devis est validé ─────
    # (statut Dolibarr : 0=brouillon, 1=validé/ouvert, 2=signé, 3=refusé, 4=facturé)
    # Le passage brouillon → validé se fait manuellement après le calcul.
    devis_url = ""
    if ctx.devis_ref:
        try:
            doli_check = DolibarrClient()
            proposal = await doli_check.get_proposal_by_ref(ctx.devis_ref)
            statut = int(proposal.get("statut", 0))
            if statut >= 1:
                from src.utils.dolibarr_urls import build_links
                devis_links = build_links(
                    {"id": ctx.devis_id, "ref": ctx.devis_ref},
                    "propal",
                    config.DOLIBARR_BASE_URL.removesuffix("/api/index.php").removesuffix("/api"),
                )
                devis_url = devis_links.get("url") or ""
                logger.info(f"s13 : devis validé (statut={statut}) — lien inclus dans l'email")
            else:
                logger.info(f"s13 : devis en brouillon (statut={statut}) — lien exclu de l'email")
        except Exception as e:
            logger.warning(f"s13 : impossible de vérifier le statut du devis → {e}")

    # ── Calculer le total HT depuis les lignes du devis ─────────────────
    total_ht = sum(
        float(line.get("subprice", 0)) * float(line.get("qty", 0))
        for line in ctx.devis_lines
        if line.get("product_type", -1) == 0  # lignes tarifaires uniquement
    )

    # ── Générer le corps de l'email via Claude ──────────────────────────
    await asyncio.sleep(13)  # anti-rate-limit : 5 req/min → 12s entre chaque appel
    ai = ClaudeClient()
    contact_prenom = ctx.client_data.get("contact_prenom") or None

    body_html = await ai.generate_email_reponse_client(
        soc_nom=ctx.soc_nom or ctx.client_data.get("soc_nom", ""),
        contact_prenom=contact_prenom,
        nom_projet=ctx.nom_projet or "",
        devis_ref=ctx.devis_ref,
        devis_url=devis_url,
        synthese_contexte=ctx.synthese_contexte or "",
        composants_isoles=ctx.composants_isoles,
        email_sentiment=ctx.email_sentiment,
        total_ht=total_ht,
    )

    if not body_html:
        logger.error("s13 : génération email vide — étape ignorée")
        ctx.add_error("s13", "Corps email vide retourné par Claude")
        return

    # Stocker dans le context
    ctx.email_reponse_client = body_html
    ctx.output_response = {
        "to": ctx.email_sender_address,
        "cc": [config.INPRESSCO_INTERNAL_EMAIL],
        "subject": f"Re: {ctx.email_subject}",
        "body_html": body_html,
        "devis_ref": ctx.devis_ref,
        "status": "pending",
    }

    # ── Envoyer l'email via Outlook Graph ────────────────────────────────
    try:
        outlook = OutlookClient()
        sent_message_id = await outlook.send_email(
            to_email=ctx.email_sender_address,
            subject=f"Re: {ctx.email_subject}",
            body_html=body_html,
            cc_emails=[config.INPRESSCO_INTERNAL_EMAIL],
            reply_to_message_id=ctx.email_id,
        )
        ctx.output_response["status"] = "sent"
        ctx.output_response["message_id"] = sent_message_id
        logger.info(
            f"s13 : email CONFIG_CLIENT_v2026 envoyé à {ctx.email_sender_address!r} "
            f"(devis {ctx.devis_ref})"
        )

        # Classer l'email envoyé dans le dossier devis Outlook
        if ctx.outlook_folder_id and sent_message_id:
            try:
                await outlook.move_message(sent_message_id, ctx.outlook_folder_id)
                logger.info(f"s13 : email envoyé classé dans dossier devis {ctx.devis_ref!r}")
            except Exception as move_err:
                logger.warning(f"s13 : classement dossier Outlook échoué → {move_err}")

    except Exception as e:
        logger.error(f"s13 : échec envoi email → {e}")
        ctx.add_error("s13_send", str(e))
        ctx.output_response["status"] = "error"
        # Ne pas bloquer le pipeline : l'email peut être renvoyé manuellement

    # ── Log note interne Dolibarr sur le devis ───────────────────────────
    if ctx.devis_id:
        try:
            doli = DolibarrClient()
            await doli.create_agenda_event({
                "label": f"Email CONFIG_CLIENT_v2026 envoyé à {ctx.email_sender_address}",
                "note": f"Email de réponse automatique envoyé après création du devis {ctx.devis_ref}.",
                "fk_element": ctx.devis_id,
                "elementtype": "propal",
                "type_code": "AC_EMAIL",
                "userownerid": config.DOLIBARR_USER_OWNER_ID,
                "fk_soc": ctx.socid,
            })
        except Exception as e:
            logger.warning(f"s13 : échec log agenda Dolibarr → {e}")

    ctx.output_silent.append({
        "type": "s13_email_reponse",
        "label": f"Email réponse envoyé à {ctx.email_sender_address} — devis {ctx.devis_ref}",
        "status": ctx.output_response.get("status", "unknown"),
    })
