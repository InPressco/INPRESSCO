"""steps/flux_a/steps.py — Tous les steps du Flux A (nouveau devis)."""
import asyncio
import logging
from datetime import datetime, timezone

from src import config
from src.connectors.dolibarr import DolibarrClient
from src.connectors.claude_client import ClaudeClient
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context
from src.middleware.pipeline import StopPipeline
from src.utils.devis_builder import build_lines
from src.utils.html_cleaner import prepare_email_for_ai
from src.utils.imposition import post_process_composants
from src.utils.pipeline_helpers import (
    log_email_to_agenda,
    read_stage_output,
    upload_attachments_to_proposal,
    write_stage_output,
)

logger = logging.getLogger(__name__)

# ── Step 1 — Récupération email ────────────────────────────────────────────

async def s01_get_email(ctx: Context) -> None:
    """Récupère le dernier email non traité du dossier DEVIS Outlook."""
    outlook = OutlookClient()
    folder_id = config.OUTLOOK_FOLDER_DEVIS
    try:
        emails = await outlook.get_emails(
            folder_id=folder_id,
            odata_filter="not(startswith(subject,'[Traité]'))",
            top=1,
        )
    except Exception:
        # ID en config périmé → résoudre par nom
        logger.warning("s01 : ID dossier DEVIS invalide, résolution par nom...")
        folder_id = await outlook.get_folder_id_by_name("DEVIS")
        if not folder_id:
            raise StopPipeline("Dossier DEVIS introuvable dans Outlook")
        logger.info(f"s01 : dossier DEVIS résolu → {folder_id}")
        emails = await outlook.get_emails(
            folder_id=folder_id,
            odata_filter="not(startswith(subject,'[Traité]'))",
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


# ── Step 2 — Extraction client + sentiment + routing (parallel) ────────────

async def s02_extract_client_ai(ctx: Context) -> None:
    """
    3 appels Claude en parallèle :
    1. extract_client_data   → ctx.client_data (skill extraction-tiers)
    2. analyse_sentiment     → ctx.email_sentiment (skill analyse-sentiment-email)
    3. classify_routing      → ctx.routing_category (skill mail-routing-inpressco)
    """
    ai = ClaudeClient()
    sender_info = f"{ctx.email_sender} <{ctx.email_sender_address}>"
    clean_body = prepare_email_for_ai(ctx.email_body)

    # Appels parallèles
    client_result, sentiment_result, routing_result = await asyncio.gather(
        ai.extract_client_data(sender_info, clean_body),
        ai.analyse_sentiment_email(sender_info, clean_body),
        ai.classify_email_routing(sender_info, clean_body),
        return_exceptions=True,
    )

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


# ── Step 3 — Routing validation + nettoyage données ──────────────────────

# Catégories qui poursuivent le pipeline Flux A (nouveau devis)
_CATEGORIES_DEVIS = {"NEW_PROJECT"}

async def s03_clean_data(ctx: Context) -> None:
    """
    1. Valide la catégorie de routing (skill mail-routing-inpressco).
       → StopPipeline si l'email n'est pas un nouveau devis client.
    2. Nettoie les espaces, filtre les données InPressco résiduelles.
    """
    # ── Routing check ──────────────────────────────────────────────────────
    cat = ctx.routing_category or "UNKNOWN"
    if cat not in _CATEGORIES_DEVIS:
        motif = f"Email classifié '{cat}' (pas un nouveau devis) — pipeline arrêté proprement."
        logger.info(motif)
        raise StopPipeline(motif)

    # ── Nettoyage données client ───────────────────────────────────────────
    data = ctx.client_data
    for key, val in data.items():
        if isinstance(val, str):
            data[key] = val.strip()

    soc = data.get("soc_nom", "") or ""
    if any(excl.lower() in soc.lower() for excl in config.INPRESSCO_EXCLUDE_NAMES):
        logger.warning(f"soc_nom contient un nom InPressco : {soc!r} → mis à null")
        data["soc_nom"] = None

    ctx.client_data = data


# ── Step 4 — Trouver ou créer le client Dolibarr ─────────────────────────

async def s04_find_or_create_client(ctx: Context) -> None:
    """Recherche le tiers dans Dolibarr. Le crée si besoin. Fallback = socid 16."""
    doli = DolibarrClient()
    data = ctx.client_data
    soc_nom = data.get("soc_nom")
    email = data.get("email")

    found = await doli.find_thirdparty(email=email, name=soc_nom)

    if found:
        ctx.socid = int(found["id"])
        ctx.soc_nom = found.get("name", soc_nom or "")
        logger.info(f"Tiers trouvé : socid={ctx.socid}, nom={ctx.soc_nom!r}")

    elif soc_nom and email:
        payload = {
            "name": soc_nom,
            "client": 1,
            "email": email,
            "name_alias": f"{data.get('contact_prenom','')} {data.get('contact_nom','')}".strip(),
        }
        for field in ("zip", "town", "address", "phone"):
            if data.get(field):
                payload[field] = data[field]

        created = await doli.create_thirdparty(payload)
        ctx.socid = int(created["id"])
        ctx.soc_nom = soc_nom
        ctx.client_created = True
        logger.info(f"Tiers créé : socid={ctx.socid}, nom={ctx.soc_nom!r}")

    else:
        ctx.socid = config.DOLIBARR_SOCID_INCONNU
        ctx.soc_nom = "CLIENT A RENSEIGNER"
        logger.warning("Client non identifiable → socid=16 (CLIENT A RENSEIGNER)")


# ── Step 5 — Récupération pièces jointes ─────────────────────────────────

async def s05_get_attachments(ctx: Context) -> None:
    """Récupère les pièces jointes non-inline de l'email."""
    if not ctx.has_attachments:
        logger.info("Pas de pièces jointes.")
        return

    outlook = OutlookClient()
    all_attachments = await outlook.get_attachments(ctx.email_id)
    ctx.attachments = [a for a in all_attachments if not a.get("isInline", True)]
    logger.info(f"{len(ctx.attachments)} pièce(s) jointe(s) non-inline récupérée(s)")


# ── Step 6 — Analyse besoin impression ───────────────────────────────────

async def s06_analyse_besoin(ctx: Context) -> None:
    """Analyse le besoin d'impression via IA. Extrait les composants structurés."""
    ai = ClaudeClient()
    clean_body = prepare_email_for_ai(ctx.email_body)
    result = await ai.analyse_besoin_impression(clean_body)

    ctx.synthese_contexte = result.get("synthese_contexte", "")
    ctx.date_livraison_souhaitee = result.get("date_livraison_souhaitee")
    composants = result.get("composants_isoles", [])

    # Post-processing Python : imposition + score (plus fiable que le LLM)
    ctx.composants_isoles = post_process_composants(composants)
    logger.info(f"Analyse besoin : {len(ctx.composants_isoles)} composant(s) identifié(s)")


# ── Step 7 — Construction des lignes de devis ─────────────────────────────

async def s07_build_devis_lines(ctx: Context) -> None:
    """Construit les lignes Dolibarr depuis les composants analysés."""
    ctx.devis_lines = build_lines(ctx.composants_isoles, ctx.synthese_contexte)
    logger.info(f"{len(ctx.devis_lines)} ligne(s) de devis construite(s)")


# ── Step 8 — Création devis dans Dolibarr ────────────────────────────────

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

    logger.info(f"Devis créé : id={ctx.devis_id}, ref={ctx.devis_ref!r}")


# ── Step 9 — Upload pièces jointes ────────────────────────────────────────

async def s09_upload_attachments(ctx: Context) -> None:
    """Upload les PJ de l'email dans le dossier du devis Dolibarr."""
    if not ctx.attachments or not ctx.devis_ref:
        return
    await upload_attachments_to_proposal(
        OutlookClient(), DolibarrClient(), ctx.email_id, ctx.devis_ref, ctx.attachments
    )


# ── Step 10 — Log email dans agenda Dolibarr ─────────────────────────────

async def s10_log_email(ctx: Context) -> None:
    """Crée un événement agenda dans Dolibarr lié au devis."""
    if not ctx.devis_id:
        logger.warning("Pas de devis_id, log agenda ignoré")
        return
    await log_email_to_agenda(
        DolibarrClient(),
        ctx.email_id,
        ctx.email_sender_address,
        ",".join(ctx.email_to_recipients),
        ctx.email_subject,
        ctx.email_body_preview,
        ctx.socid,
        ctx.devis_id,
        ctx.devis_ref,
    )


# ── Step 11 — Archivage Outlook ────────────────────────────────────────────

async def s11_archive_outlook(ctx: Context) -> None:
    """
    Crée un dossier Outlook "{ref} - {soc_nom}",
    renomme le mail "[Traité] {subject}",
    et déplace le mail dans ce dossier.
    """
    outlook = OutlookClient()

    folder_name = f"{ctx.devis_ref} - {(ctx.soc_nom or '')[:180]}"
    new_folder = await outlook.create_folder(
        parent_folder_id=config.OUTLOOK_FOLDER_DEVIS,
        display_name=folder_name,
    )

    await outlook.update_message_subject(
        ctx.email_id,
        f"[Traité] {ctx.email_subject}"
    )

    await outlook.move_message(ctx.email_id, new_folder["id"])
    logger.info(f"Email archivé dans {folder_name!r}")

    # Archivage complet : effacer le marker anti-doublon pour laisser place au prochain email
    write_stage_output(4, {"email_id": None, "devis_id": None, "devis_ref": None})


# ── Step 12 — Notification interne + bouton GO ────────────────────────────

async def s12_notify_team(ctx: Context) -> None:
    """
    Sauvegarde le contexte dans runs/pending/{devis_id}.json
    et envoie un email interne à l'équipe avec :
    - Résumé du devis (client, projet, composants, total HT)
    - Liens de validation Dolibarr (devis, client)
    - Bouton GO → /api/go/{devis_id} (déclenche s13)

    Le pipeline s'arrête ici. s13 est déclenché manuellement via le bouton GO.
    """
    import dataclasses
    from pathlib import Path

    if not ctx.devis_id:
        logger.warning("s12_notify : pas de devis_id — notification ignorée")
        return

    # ── Persister le contexte ────────────────────────────────────────────
    pending_dir = Path(__file__).parent.parent.parent.parent / "runs" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    ctx_path = pending_dir / f"{ctx.devis_id}.json"
    import json as _json
    ctx_path.write_text(_json.dumps(dataclasses.asdict(ctx), ensure_ascii=False, indent=2))
    logger.info(f"s12_notify : contexte sauvegardé → {ctx_path}")

    # ── Construire les liens Dolibarr ────────────────────────────────────
    doli_web = config.DOLIBARR_BASE_URL.removesuffix("/api/index.php").removesuffix("/api")
    devis_link = f"{doli_web}/comm/propal/card.php?id={ctx.devis_id}"
    client_link = f"{doli_web}/societe/card.php?socid={ctx.socid}" if ctx.socid else ""
    validate_link = f"{doli_web}/comm/propal/card.php?id={ctx.devis_id}&action=valid"
    go_url = f"{config.DASHBOARD_URL}/api/go/{ctx.devis_id}"

    # ── Construire le résumé des composants ─────────────────────────────
    composants_html = ""
    for c in ctx.composants_isoles:
        label = c.get("label") or c.get("type", "composant")
        qty = c.get("quantite", "")
        fmt = c.get("format", "")
        composants_html += f"<li><b>{label}</b> — qté {qty} — format {fmt}</li>"
    if not composants_html:
        composants_html = "<li><i>Aucun composant extrait</i></li>"

    total_ht = sum(
        float(line.get("subprice", 0)) * float(line.get("qty", 0))
        for line in ctx.devis_lines
        if line.get("product_type", -1) == 0
    )

    urgence = ctx.email_sentiment.get("urgence", "—")
    profil = ctx.email_sentiment.get("profil", "—")

    body_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#1a1a2e;padding:16px 24px;border-radius:8px 8px 0 0">
        <h2 style="color:#f59e0b;margin:0">⚙️ Nouveau devis à valider</h2>
        <p style="color:#d1d5db;margin:4px 0 0">{ctx.devis_ref} — {ctx.soc_nom or "Client inconnu"}</p>
      </div>

      <div style="background:#f8f9fa;padding:20px 24px;border:1px solid #e5e7eb">

        <table style="width:100%;border-collapse:collapse;margin-bottom:16px">
          <tr><td style="padding:6px 0;color:#6b7280;width:140px">Client</td>
              <td style="padding:6px 0;font-weight:bold">{ctx.soc_nom or "—"}</td></tr>
          <tr><td style="padding:6px 0;color:#6b7280">Projet</td>
              <td style="padding:6px 0">{ctx.nom_projet or "—"}</td></tr>
          <tr><td style="padding:6px 0;color:#6b7280">Référence devis</td>
              <td style="padding:6px 0;font-weight:bold;color:#1a1a2e">{ctx.devis_ref}</td></tr>
          <tr><td style="padding:6px 0;color:#6b7280">Total HT estimé</td>
              <td style="padding:6px 0;font-weight:bold">{total_ht:,.2f} €</td></tr>
          <tr><td style="padding:6px 0;color:#6b7280">Urgence</td>
              <td style="padding:6px 0">{urgence}</td></tr>
          <tr><td style="padding:6px 0;color:#6b7280">Profil client</td>
              <td style="padding:6px 0">{profil}</td></tr>
        </table>

        <p style="font-weight:bold;margin:0 0 8px">Composants identifiés :</p>
        <ul style="margin:0 0 20px;padding-left:20px">{composants_html}</ul>

        <p style="font-weight:bold;margin:0 0 10px;color:#374151">🔗 Liens Dolibarr :</p>
        <p style="margin:4px 0">
          <a href="{devis_link}" style="color:#1d4ed8">📄 Voir le devis {ctx.devis_ref}</a>
        </p>
        {"<p style='margin:4px 0'><a href='" + client_link + "' style='color:#1d4ed8'>👤 Fiche client</a></p>" if client_link else ""}
        <p style="margin:4px 0">
          <a href="{validate_link}" style="color:#059669">✅ Valider le devis dans Dolibarr</a>
        </p>

        <div style="text-align:center;margin-top:28px">
          <a href="{go_url}"
             style="background:#f59e0b;color:#1a1a2e;padding:14px 36px;
                    border-radius:8px;font-size:18px;font-weight:bold;
                    text-decoration:none;display:inline-block;letter-spacing:1px">
            🚀 GO — Envoyer l'email au client
          </a>
        </div>
        <p style="text-align:center;color:#9ca3af;font-size:12px;margin-top:12px">
          Cliquez GO uniquement après avoir validé et complété le devis dans Dolibarr.
        </p>

      </div>
    </div>
    """

    try:
        outlook = OutlookClient()
        await outlook.send_email(
            to_email=config.INPRESSCO_INTERNAL_EMAIL,
            subject=f"[GO requis] Devis {ctx.devis_ref} — {ctx.soc_nom or 'Client inconnu'}",
            body_html=body_html,
        )
        logger.info(f"s12_notify : email interne envoyé → {config.INPRESSCO_INTERNAL_EMAIL}")
    except Exception as e:
        logger.error(f"s12_notify : échec envoi email interne → {e}")
        ctx.add_error("s12_notify", str(e))

    ctx.output_silent.append({
        "type": "s12_notify_team",
        "label": f"Notification interne envoyée — GO requis pour envoyer au client ({ctx.email_sender_address})",
        "go_url": go_url,
        "status": "pending_go",
    })


# ── Step 13 — Email réponse client CONFIG_CLIENT_v2026 ────────────────────

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
        logger.warning("s12 : email_sender_address vide — réponse client ignorée")
        return
    if not ctx.devis_ref:
        logger.warning("s12 : devis_ref vide — réponse client ignorée")
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
                logger.info(f"s12 : devis validé (statut={statut}) — lien inclus dans l'email")
            else:
                logger.info(f"s12 : devis en brouillon (statut={statut}) — lien exclu de l'email")
        except Exception as e:
            logger.warning(f"s12 : impossible de vérifier le statut du devis → {e}")

    # ── Calculer le total HT depuis les lignes du devis ─────────────────
    total_ht = sum(
        float(line.get("subprice", 0)) * float(line.get("qty", 0))
        for line in ctx.devis_lines
        if line.get("product_type", -1) == 0  # lignes tarifaires uniquement
    )

    # ── Générer le corps de l'email via Claude ──────────────────────────
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
        logger.error("s12 : génération email vide — étape ignorée")
        ctx.add_error("s12", "Corps email vide retourné par Claude")
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
        await outlook.send_email(
            to_email=ctx.email_sender_address,
            subject=f"Re: {ctx.email_subject}",
            body_html=body_html,
            cc_emails=[config.INPRESSCO_INTERNAL_EMAIL],
            reply_to_message_id=ctx.email_id,
        )
        ctx.output_response["status"] = "sent"
        logger.info(
            f"s12 : email CONFIG_CLIENT_v2026 envoyé à {ctx.email_sender_address!r} "
            f"(devis {ctx.devis_ref})"
        )
    except Exception as e:
        logger.error(f"s12 : échec envoi email → {e}")
        ctx.add_error("s12_send", str(e))
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
            logger.warning(f"s12 : échec log agenda Dolibarr → {e}")

    ctx.output_silent.append({
        "type": "s12_email_reponse",
        "label": f"Email réponse envoyé à {ctx.email_sender_address} — devis {ctx.devis_ref}",
        "status": ctx.output_response.get("status", "unknown"),
    })
