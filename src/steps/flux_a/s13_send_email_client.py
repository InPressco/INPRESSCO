"""steps/flux_a/s13_send_email_client.py — Envoi de l'email de réponse CONFIG_CLIENT_v2026.

Gate 4 intégrée — 4 règles bloquantes avant envoi :
  R1 : Heure locale hors plage 7h-21h → email mis en file d'attente (non envoyé)
  R2 : total_ht = 0 avec lignes tarifaires → bloqué (message : renseigner les prix)
  R3 : Nouveau contact (client créé ce run) → event ⏸ GO Nicolas avant envoi
  R4 : Sentiment hostile ou agressif → event ⏸ GO Nicolas avant envoi

CC interne supprimé (S13a) — l'équipe reçoit déjà E1 depuis s12.
"""
import asyncio
import logging
from datetime import datetime, timezone

from src import config
from src.connectors.claude_client import ClaudeClient
from src.connectors.dolibarr import DolibarrClient
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context

logger = logging.getLogger(__name__)

# Plage horaire d'envoi autorisé (heure locale Paris)
_HOUR_MIN = 7
_HOUR_MAX = 21

# Sentiments considérés comme hostiles
_HOSTILE_SENTIMENTS = {"négatif", "agressif"}


def _get_local_hour() -> int:
    """Retourne l'heure courante en heure de Paris (CET/CEST)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Paris")).hour
    except Exception:
        # Fallback : UTC+1 (CET hiver)
        from datetime import timedelta
        return datetime.now(timezone.utc).replace(tzinfo=None).hour + 1


async def _create_pending_go_event(
    doli: DolibarrClient,
    ctx: Context,
    label: str,
    note: str,
) -> None:
    """Crée un event ⏸ GO dans Dolibarr agenda."""
    try:
        await doli.create_agenda_event({
            "label": label,
            "note":  note,
            "datep": 0,
            "datef": 0,
            "fk_element":  ctx.devis_id or 0,
            "elementtype": "propal",
            "type_code":   "AC_OTH",
            "userownerid": config.DOLIBARR_USER_OWNER_ID,
            "fk_soc":      ctx.socid,
            "done":        0,
        })
    except Exception as e:
        logger.warning(f"s13 gate4: échec création event ⏸ → {e}")


async def s13_send_email_client(ctx: Context) -> None:
    """
    Génère et envoie l'email de réponse CONFIG_CLIENT_v2026 au client.
    Applique Gate 4 (4 règles) avant tout envoi.
    """
    if not ctx.email_sender_address:
        logger.warning("s13: email_sender_address vide — réponse client ignorée")
        return
    if not ctx.devis_ref:
        logger.warning("s13: devis_ref vide — réponse client ignorée")
        return

    doli = DolibarrClient()

    # ── Gate 4 — R1 : Heure raisonnable ──────────────────────────────────
    current_hour = _get_local_hour()
    if current_hour < _HOUR_MIN or current_hour > _HOUR_MAX:
        logger.info(
            f"s13 gate4[R1]: heure={current_hour}h — hors plage {_HOUR_MIN}h-{_HOUR_MAX}h "
            f"→ email mis en file d'attente (non envoyé)"
        )
        ctx.output_response = {
            "to":       ctx.email_sender_address,
            "subject":  f"Re: {ctx.email_subject}",
            "devis_ref": ctx.devis_ref,
            "status":   "queued_until_8h",
        }
        ctx.output_silent.append({
            "type":   "s13_gate4_queued",
            "label":  f"Email mis en file d'attente (heure={current_hour}h) — devis {ctx.devis_ref}",
            "status": "queued",
        })
        return

    # ── Gate 4 — R2 : Total HT non nul ───────────────────────────────────
    total_ht = sum(
        float(line.get("subprice", 0)) * float(line.get("qty", 0))
        for line in ctx.devis_lines
        if line.get("product_type", -1) == 0
    )
    has_tarif_lines = any(
        line.get("product_type", -1) == 0 for line in ctx.devis_lines
    )
    if has_tarif_lines and total_ht == 0:
        logger.warning(
            f"s13 gate4[R2]: total_ht=0 avec lignes tarifaires — "
            f"email bloqué (renseigner les prix dans Dolibarr)"
        )
        ctx.output_response = {
            "to":       ctx.email_sender_address,
            "subject":  f"Re: {ctx.email_subject}",
            "devis_ref": ctx.devis_ref,
            "status":   "blocked_zero_price",
        }
        ctx.output_silent.append({
            "type":   "s13_gate4_blocked",
            "label":  f"Email bloqué — prix = 0 sur devis {ctx.devis_ref}",
            "status": "blocked",
        })
        return

    # ── Gate 4 — R3 : Nouveau contact → ⏸ GO avant envoi ────────────────
    if ctx.client_created:
        await _create_pending_go_event(
            doli, ctx,
            label=f"⏸ réponse-client — nouveau contact — {ctx.devis_ref}",
            note=(
                f"Nouveau tiers créé ce run : {ctx.soc_nom} ({ctx.email_sender_address}).\n"
                f"Devis : {ctx.devis_ref}\n"
                f"Valider l'email avant envoi au client."
            ),
        )
        logger.info(
            f"s13 gate4[R3]: nouveau contact {ctx.email_sender_address!r} "
            f"→ event ⏸ créé — email non envoyé"
        )
        ctx.output_response = {
            "to":       ctx.email_sender_address,
            "subject":  f"Re: {ctx.email_subject}",
            "devis_ref": ctx.devis_ref,
            "status":   "pending_go_new_contact",
        }
        return

    # ── Gate 4 — R4 : Sentiment hostile → ⏸ GO avant envoi ──────────────
    sentiment = (ctx.email_sentiment or {}).get("sentiment", "")
    if sentiment in _HOSTILE_SENTIMENTS:
        await _create_pending_go_event(
            doli, ctx,
            label=f"⏸ réponse-client — ton hostile — {ctx.devis_ref}",
            note=(
                f"Email source avec sentiment={sentiment!r}.\n"
                f"Client : {ctx.soc_nom} ({ctx.email_sender_address})\n"
                f"Devis : {ctx.devis_ref}\n"
                f"Valider le ton de la réponse avant envoi."
            ),
        )
        logger.info(
            f"s13 gate4[R4]: sentiment={sentiment!r} — hostile "
            f"→ event ⏸ créé — email non envoyé"
        )
        ctx.output_response = {
            "to":       ctx.email_sender_address,
            "subject":  f"Re: {ctx.email_subject}",
            "devis_ref": ctx.devis_ref,
            "status":   "pending_go_hostile_sentiment",
        }
        return

    # ── Gate 4 passée — construire l'URL du devis si validé ──────────────
    devis_url = ""
    if ctx.devis_ref:
        try:
            proposal = await doli.get_proposal_by_ref(ctx.devis_ref)
            statut   = int(proposal.get("statut", 0))
            if statut >= 1:
                from src.utils.dolibarr_urls import build_links
                devis_links = build_links(
                    {"id": ctx.devis_id, "ref": ctx.devis_ref},
                    "propal",
                    config.DOLIBARR_BASE_URL.removesuffix("/api/index.php").removesuffix("/api"),
                )
                devis_url = devis_links.get("url") or ""
                logger.info(f"s13: devis validé (statut={statut}) — lien inclus")
            else:
                logger.info(f"s13: devis brouillon (statut={statut}) — lien exclu")
        except Exception as e:
            logger.warning(f"s13: vérification statut devis → {e}")

    # ── Générer le corps de l'email via Claude ────────────────────────────
    await asyncio.sleep(13)  # anti-rate-limit : 5 req/min
    ai              = ClaudeClient()
    contact_prenom  = ctx.client_data.get("contact_prenom") or None

    body_html = await ai.generate_email_reponse_client(
        soc_nom           = ctx.soc_nom or ctx.client_data.get("soc_nom", ""),
        contact_prenom    = contact_prenom,
        nom_projet        = ctx.nom_projet or "",
        devis_ref         = ctx.devis_ref,
        devis_url         = devis_url,
        synthese_contexte = ctx.synthese_contexte or "",
        composants_isoles = ctx.composants_isoles,
        email_sentiment   = ctx.email_sentiment,
        total_ht          = total_ht,
    )

    if not body_html:
        logger.error("s13: génération email vide — étape ignorée")
        ctx.add_error("s13", "Corps email vide retourné par Claude")
        return

    ctx.email_reponse_client = body_html
    ctx.output_response = {
        "to":       ctx.email_sender_address,
        "subject":  f"Re: {ctx.email_subject}",
        "body_html": body_html,
        "devis_ref": ctx.devis_ref,
        "status":   "pending",
    }

    # ── Envoyer via Outlook Graph (sans CC interne — E3 supprimé) ────���────
    try:
        outlook         = OutlookClient()
        sent_message_id = await outlook.send_email(
            to_email          = ctx.email_sender_address,
            subject           = f"Re: {ctx.email_subject}",
            body_html         = body_html,
            cc_emails         = [],       # CC interne supprimé — équipe reçoit E1 depuis s12
            reply_to_message_id = ctx.email_id,
        )
        ctx.output_response["status"]     = "sent"
        ctx.output_response["message_id"] = sent_message_id
        logger.info(
            f"s13: email CONFIG_CLIENT_v2026 envoyé à {ctx.email_sender_address!r} "
            f"(devis {ctx.devis_ref})"
        )

        if ctx.outlook_folder_id and sent_message_id:
            try:
                await outlook.move_message(sent_message_id, ctx.outlook_folder_id)
                logger.info(f"s13: email classé dans dossier devis {ctx.devis_ref!r}")
            except Exception as move_err:
                logger.warning(f"s13: classement dossier Outlook échoué → {move_err}")

    except Exception as e:
        logger.error(f"s13: échec envoi email → {e}")
        ctx.add_error("s13_send", str(e))
        ctx.output_response["status"] = "error"

    # ── Log note interne Dolibarr ─────────────────────────────────────────
    if ctx.devis_id:
        try:
            await doli.create_agenda_event({
                "label":       f"Email CONFIG_CLIENT_v2026 envoyé à {ctx.email_sender_address}",
                "note":        f"Email de réponse automatique envoyé — devis {ctx.devis_ref}.",
                "fk_element":  ctx.devis_id,
                "elementtype": "propal",
                "type_code":   "AC_EMAIL",
                "userownerid": config.DOLIBARR_USER_OWNER_ID,
                "fk_soc":      ctx.socid,
            })
        except Exception as e:
            logger.warning(f"s13: échec log agenda Dolibarr → {e}")

    ctx.output_silent.append({
        "type":   "s13_email_reponse",
        "label":  f"Email réponse envoyé à {ctx.email_sender_address} — devis {ctx.devis_ref}",
        "status": ctx.output_response.get("status", "unknown"),
    })
