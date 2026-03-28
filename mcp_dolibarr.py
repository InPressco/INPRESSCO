"""mcp_dolibarr.py — Serveur MCP pour l'API Dolibarr InPressco.

Expose les outils Dolibarr directement dans Claude Code :

  Tiers
  - find_thirdparty       : rechercher un tiers (email / nom)
  - get_thirdparty        : lire un tiers par ID
  - list_thirdparties     : lister les tiers

  Devis
  - get_proposal          : lire un devis par référence (ex: PRO2025-0042)
  - list_proposals        : lister les devis (filtres optionnels)

  Commandes
  - get_order             : lire une commande par référence (ex: CO2025-0012)
  - list_orders           : lister les commandes client

  Factures
  - get_invoice           : lire une facture par référence (ex: FA2025-0042)
  - list_invoices         : lister les factures (filtres : tiers, statut, période)
  - get_invoice_payments  : paiements reçus pour une facture

  Bons de livraison
  - get_shipment          : lire un bon de livraison par ID
  - list_shipments        : lister les bons de livraison

  Produits
  - list_products         : lister les produits/services

Lecture seule — aucun outil d'écriture.
"""

import os
import httpx
from mcp.server.fastmcp import FastMCP

from src.utils.dolibarr_urls import enrich as _enrich_doli

# ── Config ──────────────────────────────────────────────────────────────────

BASE_URL = os.getenv("DOLIBARR_BASE_URL", "").rstrip("/")
API_KEY  = os.getenv("DOLIBARR_API_KEY", "")
WEB_URL  = BASE_URL.removesuffix("/api/index.php")

HEADERS = {
    "DOLAPIKEY": API_KEY,
    "Accept": "application/json",
}

mcp = FastMCP("dolibarr-inpressco")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get(path: str, params: dict | None = None):
    url = f"{BASE_URL}/{path.lstrip('/')}"
    resp = httpx.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _enrich(obj: dict, module: str) -> dict:
    return _enrich_doli(obj, module, WEB_URL)


# ── Outils Tiers ────────────────────────────────────────────────────────────

@mcp.tool()
def find_thirdparty(email: str = "", name: str = "") -> dict:
    """Rechercher un tiers Dolibarr par email et/ou nom.

    Args:
        email: Adresse email exacte du tiers.
        name:  Nom (partiel) du tiers — recherche avec LIKE.

    Returns:
        Le premier tiers trouvé, ou {"found": false} si aucun résultat.
    """
    if email:
        results = _get("thirdparties", {"sqlfilters": f"(t.email:=:'{email}')"})
        if results:
            return results[0]

    if name:
        results = _get("thirdparties", {"sqlfilters": f"(t.nom:like:'%{name}%')"})
        if results:
            return results[0]

    return {"found": False}


@mcp.tool()
def get_thirdparty(thirdparty_id: int) -> dict:
    """Lire un tiers Dolibarr par son ID.

    Args:
        thirdparty_id: ID numérique du tiers.

    Returns:
        L'objet tiers complet.
    """
    return _get(f"thirdparties/{thirdparty_id}")


@mcp.tool()
def list_thirdparties(limit: int = 20, page: int = 0, sortfield: str = "t.rowid", sortorder: str = "DESC") -> list:
    """Lister les tiers Dolibarr.

    Args:
        limit:     Nombre max de résultats (défaut 20, max 500).
        page:      Numéro de page (défaut 0).
        sortfield: Champ de tri (défaut t.rowid).
        sortorder: ASC ou DESC (défaut DESC).

    Returns:
        Liste de tiers.
    """
    return _get("thirdparties", {
        "limit": min(limit, 500),
        "page": page,
        "sortfield": sortfield,
        "sortorder": sortorder,
    })


# ── Outils Devis ────────────────────────────────────────────────────────────

@mcp.tool()
def get_proposal(ref: str) -> dict:
    """Lire un devis Dolibarr par sa référence.

    Args:
        ref: Référence du devis, ex: PRO2025-0042.

    Returns:
        L'objet devis complet avec ses lignes.
    """
    return _enrich(_get(f"proposals/ref/{ref}", {"contact_list": 1}), "propal")


@mcp.tool()
def list_proposals(
    thirdparty_id: int = 0,
    status: str = "",
    datestart: str = "",
    dateend: str = "",
    limit: int = 20,
    page: int = 0,
    sortorder: str = "DESC"
) -> list:
    """Lister les devis Dolibarr.

    Args:
        thirdparty_id: Filtrer par ID tiers (0 = tous).
        status:        Filtrer par statut : draft | validated | signed | notsigned | closed.
        datestart:     Date de début au format YYYY-MM-DD (ex: 2025-01-01).
        dateend:       Date de fin au format YYYY-MM-DD (ex: 2025-12-31).
        limit:         Nombre max de résultats (défaut 20, max 500).
        page:          Numéro de page (défaut 0).
        sortorder:     ASC ou DESC (défaut DESC = plus récents en premier).

    Returns:
        Liste de devis.
    """
    params: dict = {
        "limit": min(limit, 500),
        "page": page,
        "sortfield": "t.rowid",
        "sortorder": sortorder,
    }
    if thirdparty_id:
        params["thirdparty_ids"] = thirdparty_id
    if status:
        params["status"] = status
    if datestart:
        params["datestart"] = datestart
    if dateend:
        params["dateend"] = dateend

    return [_enrich(p, "propal") for p in _get("proposals", params)]


# ── Outils Commandes ────────────────────────────────────────────────────────

@mcp.tool()
def get_order(ref: str) -> dict:
    """Lire une commande client Dolibarr par sa référence.

    Args:
        ref: Référence de la commande, ex: CO2025-0012.

    Returns:
        L'objet commande complet avec ses lignes.
    """
    return _enrich(_get(f"orders/ref/{ref}", {"contact_list": 1}), "commande")


@mcp.tool()
def list_orders(
    thirdparty_id: int = 0,
    status: str = "",
    datestart: str = "",
    dateend: str = "",
    limit: int = 20,
    page: int = 0,
    sortorder: str = "DESC"
) -> list:
    """Lister les commandes client Dolibarr.

    Args:
        thirdparty_id: Filtrer par ID tiers (0 = tous).
        status:        Filtrer par statut : 0=brouillon | 1=validée | 2=expédiée | 3=annulée.
        datestart:     Date de début au format YYYY-MM-DD (ex: 2025-01-01).
        dateend:       Date de fin au format YYYY-MM-DD (ex: 2025-12-31).
        limit:         Nombre max de résultats (défaut 20, max 500).
        page:          Numéro de page (défaut 0).
        sortorder:     ASC ou DESC (défaut DESC = plus récentes en premier).

    Returns:
        Liste de commandes.
    """
    params: dict = {
        "limit": min(limit, 500),
        "page": page,
        "sortfield": "t.rowid",
        "sortorder": sortorder,
    }
    if thirdparty_id:
        params["thirdparty_ids"] = thirdparty_id
    if status != "":
        params["status"] = status
    if datestart:
        params["datestart"] = datestart
    if dateend:
        params["dateend"] = dateend

    return [_enrich(o, "commande") for o in _get("orders", params)]


# ── Outils Factures ──────────────────────────────────────────────────────────

@mcp.tool()
def get_invoice(ref: str) -> dict:
    """Lire une facture Dolibarr par sa référence.

    Args:
        ref: Référence de la facture, ex: FA2025-0042.

    Returns:
        L'objet facture complet avec ses lignes.
    """
    return _enrich(_get(f"invoices/ref/{ref}", {"contact_list": 1}), "facture")


@mcp.tool()
def list_invoices(
    thirdparty_id: int = 0,
    status: str = "",
    datestart: str = "",
    dateend: str = "",
    limit: int = 20,
    page: int = 0,
    sortorder: str = "DESC"
) -> list:
    """Lister les factures Dolibarr.

    Args:
        thirdparty_id: Filtrer par ID tiers (0 = tous).
        status:        Filtrer par statut : 0=brouillon | 1=validée/impayée | 2=payée | 3=abandonnée.
        datestart:     Date de début au format YYYY-MM-DD (ex: 2025-01-01).
        dateend:       Date de fin au format YYYY-MM-DD (ex: 2025-12-31).
        limit:         Nombre max de résultats (défaut 20, max 500).
        page:          Numéro de page (défaut 0).
        sortorder:     ASC ou DESC (défaut DESC = plus récentes en premier).

    Returns:
        Liste de factures.
    """
    params: dict = {
        "limit": min(limit, 500),
        "page": page,
        "sortfield": "t.rowid",
        "sortorder": sortorder,
    }
    if thirdparty_id:
        params["thirdparty_ids"] = thirdparty_id
    if status != "":
        params["status"] = status
    if datestart:
        params["datestart"] = datestart
    if dateend:
        params["dateend"] = dateend

    return [_enrich(f, "facture") for f in _get("invoices", params)]


@mcp.tool()
def get_invoice_payments(invoice_id: int) -> list:
    """Lister les paiements reçus pour une facture Dolibarr.

    Args:
        invoice_id: ID numérique de la facture.

    Returns:
        Liste des paiements associés à la facture (date, montant, mode de paiement).
    """
    return _get(f"invoices/{invoice_id}/payments")


# ── Outils Bons de livraison ─────────────────────────────────────────────────

@mcp.tool()
def get_shipment(shipment_id: int) -> dict:
    """Lire un bon de livraison Dolibarr par son ID.

    Args:
        shipment_id: ID numérique du bon de livraison.

    Returns:
        L'objet bon de livraison complet avec ses lignes.
    """
    return _enrich(_get(f"shipments/{shipment_id}"), "expedition")


@mcp.tool()
def list_shipments(
    thirdparty_id: int = 0,
    limit: int = 20,
    page: int = 0,
    sortorder: str = "DESC"
) -> list:
    """Lister les bons de livraison Dolibarr.

    Args:
        thirdparty_id: Filtrer par ID tiers (0 = tous).
        limit:         Nombre max de résultats (défaut 20).
        page:          Numéro de page (défaut 0).
        sortorder:     ASC ou DESC (défaut DESC = plus récents en premier).

    Returns:
        Liste de bons de livraison.
    """
    params: dict = {
        "limit": min(limit, 100),
        "page": page,
        "sortfield": "t.rowid",
        "sortorder": sortorder,
    }
    if thirdparty_id:
        params["thirdparty_ids"] = thirdparty_id

    return [_enrich(s, "expedition") for s in _get("shipments", params)]


# ── Outils Produits ─────────────────────────────────────────────────────────

@mcp.tool()
def list_products(
    search: str = "",
    limit: int = 20,
    page: int = 0
) -> list:
    """Lister les produits/services Dolibarr.

    Args:
        search: Filtrer par nom (partiel).
        limit:  Nombre max de résultats (défaut 20).
        page:   Numéro de page.

    Returns:
        Liste de produits.
    """
    params: dict = {
        "limit": min(limit, 100),
        "page": page,
        "sortfield": "t.label",
        "sortorder": "ASC",
    }
    if search:
        params["sqlfilters"] = f"(t.label:like:'%{search}%')"

    return _get("products", params)


# ── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
