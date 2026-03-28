"""tests/test_dolibarr.py — Test connexion Dolibarr + données financières.

Vérifie :
  ✓ Connexion API (DOLIBARR_API_KEY)
  ✓ GET /thirdparties        → derniers clients
  ✓ GET /proposals           → derniers devis
  ✓ GET /invoices            → factures clients (CA + impayées)
  ✓ GET /supplier_invoices   → factures fournisseurs impayées

Usage :
  python tests/test_dolibarr.py
  python tests/test_dolibarr.py --full    # affiche le détail JSON brut
"""

import sys as _sys
import os as _os
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()
_os.environ.setdefault("OPENAI_API_KEY", "dummy")
_os.environ.setdefault("OUTLOOK_TENANT_ID", "dummy")
_os.environ.setdefault("OUTLOOK_CLIENT_ID", "dummy")
_os.environ.setdefault("OUTLOOK_CLIENT_SECRET", "dummy")
_os.environ.setdefault("OUTLOOK_REFRESH_TOKEN", "dummy")

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
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

BASE = config.DOLIBARR_BASE_URL
HEADERS = {"DOLAPIKEY": config.DOLIBARR_API_KEY, "Accept": "application/json"}


async def get(client: httpx.AsyncClient, path: str, params: dict = None) -> tuple[int, any]:
    try:
        r = await client.get(f"{BASE}{path}", params=params or {}, headers=HEADERS, timeout=15)
        try:
            data = r.json()
        except Exception:
            data = r.text
        return r.status_code, data
    except Exception as e:
        return 0, str(e)


def fmt_euro(val) -> str:
    try:
        return f"{float(val):,.2f} €".replace(",", " ")
    except Exception:
        return str(val)


def statut_facture(statut: int) -> str:
    return {0: "Brouillon", 1: "Impayée", 2: "Payée", 3: "Abandonnée"}.get(int(statut), str(statut))


async def run(full: bool = False):
    section("Test connexion Dolibarr")
    info(f"URL : {BASE}")
    info(f"Clé : {config.DOLIBARR_API_KEY[:8]}...")

    async with httpx.AsyncClient() as client:

        # ── 1. Connexion basique ───────────────────────────────────────────
        subsection("1. Connexion (GET /status)")
        code, data = await get(client, "/status")
        if code == 200:
            ok(f"HTTP {code} — Dolibarr {data.get('version','?')} connecté")
        else:
            fail(f"HTTP {code} — {str(data)[:120]}")
            print(c(RED, "\n  Arrêt : connexion impossible. Vérifier DOLIBARR_API_KEY dans .env"))
            return

        # ── 2. Tiers ──────────────────────────────────────────────────────
        subsection("2. Tiers (GET /thirdparties)")
        code, data = await get(client, "/thirdparties", {
            "limit": 5, "sortfield": "t.rowid", "sortorder": "DESC", "mode": 1
        })
        if code == 200 and isinstance(data, list):
            ok(f"{len(data)} tiers récupérés")
            for t in data[:3]:
                info(f"  [{t.get('id')}] {t.get('name','?')} — {t.get('email','—')}")
            if full:
                print(json.dumps(data[0], indent=2, ensure_ascii=False))
        else:
            fail(f"HTTP {code} — {str(data)[:120]}")

        # ── 3. Devis ──────────────────────────────────────────────────────
        subsection("3. Devis (GET /proposals)")
        code, data = await get(client, "/proposals", {"limit": 5})
        if code == 200 and isinstance(data, list):
            ok(f"{len(data)} devis récupérés")
            for p in data[:3]:
                montant = fmt_euro(p.get("total_ttc", 0))
                statut = {0:"Brouillon", 1:"Validé", 2:"Signé", 3:"Refusé", 4:"Expiré"}.get(int(p.get("statut",0)), "?")
                info(f"  [{p.get('ref','?')}] {p.get('socnom','?')} — {montant} — {statut}")
            if full:
                print(json.dumps(data[0], indent=2, ensure_ascii=False))
        else:
            fail(f"HTTP {code} — {str(data)[:120]}")

        # ── 4. Factures clients — CA + impayées ───────────────────────────
        subsection("4. Factures clients (GET /invoices)")

        # CA du mois en cours
        now = datetime.now(timezone.utc)
        debut_mois = int(datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp())

        code, all_inv = await get(client, "/invoices", {"limit": 100, "type": 0})

        if code == 200 and isinstance(all_inv, list):
            ok(f"{len(all_inv)} factures récupérées (100 max)")

            # CA mois en cours (factures validées ou payées)
            ca_mois = sum(
                float(f.get("total_ht") or 0)
                for f in all_inv
                if int(f.get("date", 0) or 0) >= debut_mois
                and int(f.get("statut", 0) or 0) in (1, 2)
            )

            # Impayées
            impayes = [f for f in all_inv if int(f.get("statut", 0) or 0) == 1]
            total_impaye = sum(float(f.get("total_ttc") or 0) for f in impayes)

            ok(f"CA mois en cours (HT) : {c(B+G, fmt_euro(ca_mois))}")
            if impayes:
                warn(f"{len(impayes)} facture(s) impayée(s) — {fmt_euro(total_impaye)} TTC")
                for f in impayes[:5]:
                    echeance = f.get("date_lim_reglement")
                    echeance_str = datetime.fromtimestamp(int(echeance)).strftime("%d/%m/%Y") if echeance else "—"
                    info(f"  [{f.get('ref','?')}] {f.get('socnom','?')} — {fmt_euro(f.get('total_ttc',0))} — échéance {echeance_str}")
            else:
                ok("Aucune facture impayée")

            if full and all_inv:
                print(json.dumps(all_inv[0], indent=2, ensure_ascii=False))
        else:
            fail(f"HTTP {code} — {str(data)[:120]}")

        # ── 5. Factures fournisseurs ──────────────────────────────────────
        subsection("5. Factures fournisseurs (GET /supplier_invoices)")
        code, sup_inv = await get(client, "/supplier_invoices", {"limit": 50})

        if code == 200 and isinstance(sup_inv, list):
            ok(f"{len(sup_inv)} factures fournisseurs récupérées")
            impayes_four = [f for f in sup_inv if int(f.get("statut", 0) or 0) == 1]
            total_four = sum(float(f.get("total_ttc") or 0) for f in impayes_four)

            if impayes_four:
                warn(f"{len(impayes_four)} facture(s) fournisseur impayée(s) — {fmt_euro(total_four)} TTC")
                for f in impayes_four[:5]:
                    info(f"  [{f.get('ref','?')}] {f.get('socnom','?')} — {fmt_euro(f.get('total_ttc',0))}")
            else:
                ok("Aucune facture fournisseur impayée")

            if full and sup_inv:
                print(json.dumps(sup_inv[0], indent=2, ensure_ascii=False))
        elif code == 404:
            warn("Endpoint /supplier_invoices non accessible avec cette clé")
        else:
            fail(f"HTTP {code} — {str(data)[:120]}")

        # ── 6. Commandes ──────────────────────────────────────────────────
        subsection("6. Commandes (GET /orders)")
        code, orders = await get(client, "/orders", {"limit": 5})
        if code == 200 and isinstance(orders, list):
            ok(f"{len(orders)} commandes récupérées")
            for o in orders[:3]:
                info(f"  [{o.get('ref','?')}] {o.get('socnom','?')} — {fmt_euro(o.get('total_ttc',0))}")
        elif code == 404:
            warn("Endpoint /orders non accessible avec cette clé")
        else:
            fail(f"HTTP {code} — {str(data)[:120]}")

        # ── Résumé ────────────────────────────────────────────────────────
        section("Résumé — champs JSON disponibles")
        info("Relancer avec --full pour voir le JSON brut du premier objet de chaque endpoint")
        info("Ces champs seront utilisés pour le dashboard et le pipeline")
        print()


if __name__ == "__main__":
    asyncio.run(run(full=FULL))
