"""steps/flux_a/s12_notify_team.py — Notification interne + bouton GO pour envoi client."""
import dataclasses
import json
import logging
from pathlib import Path

from src import config
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context

logger = logging.getLogger(__name__)


async def s12_notify_team(ctx: Context) -> None:
    """
    Sauvegarde le contexte dans runs/pending/{devis_id}.json
    et envoie un email interne à l'équipe avec :
    - Résumé du devis (client, projet, composants, total HT)
    - Liens de validation Dolibarr (devis, client)
    - Bouton GO → /api/go/{devis_id} (déclenche s13)

    Le pipeline s'arrête ici. s13 est déclenché manuellement via le bouton GO.
    """
    if not ctx.devis_id:
        logger.warning("s12_notify : pas de devis_id — notification ignorée")
        return

    # ── Persister le contexte ────────────────────────────────────────────
    pending_dir = Path(__file__).parent.parent.parent.parent / "runs" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    ctx_path = pending_dir / f"{ctx.devis_id}.json"
    ctx_path.write_text(json.dumps(dataclasses.asdict(ctx), ensure_ascii=False, indent=2))
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
