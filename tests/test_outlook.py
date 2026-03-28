"""tests/test_outlook.py — Diagnostic connexion Microsoft Graph / Outlook.

Vérifie :
  ✓ Token OAuth2 (client credentials)
  ✓ Accès boîte contact@in-pressco.com
  ✓ Liste des dossiers mail
  ✓ Lecture des derniers emails (sujet + expéditeur)
  ✓ IDs dossiers Outlook (utiles pour OUTLOOK_FOLDER_*)

Usage :
  python tests/test_outlook.py
  python tests/test_outlook.py --full    # affiche JSON brut du premier email
"""

import sys as _sys
import os as _os
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()
_os.environ.setdefault("OPENAI_API_KEY", "dummy")
_os.environ.setdefault("ANTHROPIC_API_KEY", "dummy")
_os.environ.setdefault("DOLIBARR_API_KEY", "dummy")

import asyncio
import json
import sys
from datetime import datetime

import httpx
import msal

from src import config

# ── Couleurs ───────────────────────────────────────────────────────────────
R="\033[0m"; B="\033[1m"; DIM="\033[2m"
G="\033[32m"; Y="\033[33m"; RED="\033[31m"; C="\033[36m"; GR="\033[90m"
def c(col,t): return f"{col}{t}{R}"
def hr(ch="─",w=70): print(c(GR, ch*w))
def section(t): print(); hr("═"); print(c(B+C, f"  {t}")); hr("═")
def subsection(t): print(); print(c(B, f"  ▸ {t}")); hr("·",50)
def ok(m): print(f"    {c(G,'✓')}  {m}")
def warn(m): print(f"    {c(Y,'⚠')}  {c(Y,m)}")
def fail(m): print(f"    {c(RED,'✗')}  {c(RED,m)}")
def info(m): print(f"    {c(GR,'·')}  {m}")

FULL = "--full" in sys.argv
GRAPH_BASE = config.OUTLOOK_GRAPH_BASE  # https://graph.microsoft.com/v1.0/users/contact@in-pressco.com


def get_token() -> str | None:
    """Obtenir un access token via client credentials (app-only)."""
    app = msal.ConfidentialClientApplication(
        client_id=config.OUTLOOK_CLIENT_ID,
        client_credential=config.OUTLOOK_CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{config.OUTLOOK_TENANT_ID}"
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" in result:
        return result["access_token"]
    error = result.get("error_description") or result.get("error") or str(result)
    fail(f"Token refusé : {error}")
    return None


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


async def graph_get(client: httpx.AsyncClient, token: str, path: str, params: dict = None):
    url = f"{GRAPH_BASE}{path}"
    try:
        r = await client.get(url, headers=headers(token), params=params or {}, timeout=15)
        try:
            data = r.json()
        except Exception:
            data = r.text
        return r.status_code, data
    except Exception as e:
        return 0, str(e)


async def run():
    section("Test connexion Microsoft Graph — Outlook")
    info(f"Tenant  : {config.OUTLOOK_TENANT_ID}")
    info(f"App ID  : {config.OUTLOOK_CLIENT_ID}")
    info(f"Boîte   : {config.OUTLOOK_USER_EMAIL}")

    # ── 1. Token ──────────────────────────────────────────────────────────
    subsection("1. Authentification (client credentials)")
    token = get_token()
    if not token:
        warn("Causes possibles :")
        info("  • Secret expiré ou invalide dans Azure AD")
        info("  • Permissions applicatives non accordées (Mail.Read / Mail.ReadWrite)")
        info("  • Consentement administrateur manquant")
        return
    ok(f"Token obtenu ({token[:20]}...)")

    async with httpx.AsyncClient() as client:

        # ── 2. Profil boîte ───────────────────────────────────────────────
        subsection("2. Accès boîte mail")
        code, data = await graph_get(client, token, "")
        if code == 200:
            ok(f"Boîte accessible : {data.get('displayName','?')} <{data.get('mail','?')}>")
            if FULL:
                print(json.dumps(data, indent=2, ensure_ascii=False))
        elif code == 403:
            fail(f"HTTP 403 — Permissions insuffisantes")
            warn("Dans Azure AD → app inpressco-claude → Autorisations API")
            warn("Ajouter : Mail.Read (Application) + Mail.ReadWrite (Application)")
            warn("Puis cliquer : Accorder le consentement administrateur")
            return
        elif code == 404:
            fail(f"HTTP 404 — Utilisateur introuvable : {config.OUTLOOK_USER_EMAIL}")
            warn("Vérifier OUTLOOK_USER_EMAIL dans .env")
            return
        else:
            fail(f"HTTP {code} — {str(data)[:200]}")
            return

        # ── 3. Dossiers mail ──────────────────────────────────────────────
        subsection("3. Dossiers mail (mailFolders)")
        code, data = await graph_get(client, token, "/mailFolders", {"$top": 20})
        if code == 200 and "value" in data:
            folders = data["value"]
            ok(f"{len(folders)} dossiers trouvés")
            for f in folders:
                info(f"  [{f.get('id','')}]")
                info(f"    Nom : {f.get('displayName','?')} — {f.get('totalItemCount',0)} emails")
        else:
            fail(f"HTTP {code} — {str(data)[:200]}")

        # ── 4. Sous-dossiers Boîte de réception ───────────────────────────
        subsection("4. Sous-dossiers Boîte de réception")
        # Trouver l'ID de la boîte de réception
        inbox_id = None
        if code == 200 and "value" in data:
            for f in data.get("value", []):
                if f.get("displayName", "").lower() in ("boîte de réception", "inbox"):
                    inbox_id = f.get("id")
                    break

        if inbox_id:
            code2, data2 = await graph_get(client, token, f"/mailFolders/{inbox_id}/childFolders")
            if code2 == 200 and "value" in data2:
                subfolders = data2["value"]
                if subfolders:
                    ok(f"{len(subfolders)} sous-dossiers")
                    for f in subfolders:
                        info(f"  [{f.get('id','')}] {f.get('displayName','?')}")
                else:
                    info("Aucun sous-dossier dans la boîte de réception")
            else:
                warn("Impossible de lister les sous-dossiers")
        else:
            info("Boîte de réception non identifiée automatiquement")

        # ── 5. Derniers emails ────────────────────────────────────────────
        subsection("5. Derniers emails reçus (Boîte de réception)")
        code, data = await graph_get(client, token, "/mailFolders/inbox/messages", {
            "$top": 5,
            "$select": "id,subject,from,receivedDateTime,hasAttachments,isRead",
            "$orderby": "receivedDateTime desc"
        })
        if code == 200 and "value" in data:
            emails = data["value"]
            ok(f"{len(emails)} emails récupérés")
            for m in emails:
                sender = m.get("from", {}).get("emailAddress", {})
                date_str = m.get("receivedDateTime", "")[:10]
                read_flag = "" if m.get("isRead") else c(Y, " [non lu]")
                attach_flag = c(C, " 📎") if m.get("hasAttachments") else ""
                info(f"  {date_str} | {sender.get('name','?')} <{sender.get('address','?')}>{read_flag}{attach_flag}")
                info(f"           Sujet : {m.get('subject','(sans sujet)')[:80]}")
            if FULL and emails:
                print(json.dumps(emails[0], indent=2, ensure_ascii=False))
        elif code == 403:
            fail("HTTP 403 — Permissions Mail.Read manquantes ou consentement non accordé")
        else:
            fail(f"HTTP {code} — {str(data)[:200]}")

    # ── Résumé ────────────────────────────────────────────────────────────
    section("Résumé")
    ok("Connexion Microsoft Graph opérationnelle")
    info("Copier les IDs de dossiers ci-dessus dans src/config.py :")
    info("  OUTLOOK_FOLDER_DEVIS  = ID du dossier 'Devis' ou 'Étude en cours'")
    info("  OUTLOOK_FOLDER_ETUDE  = ID du sous-dossier cible après traitement")
    info("")
    info("Relancer avec --full pour voir le JSON brut du premier email")
    print()


if __name__ == "__main__":
    asyncio.run(run())
