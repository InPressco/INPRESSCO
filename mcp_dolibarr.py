"""mcp_dolibarr.py — Serveur MCP pour l'API Dolibarr InPressco.

Expose les outils Dolibarr directement dans Claude Code :

  Tiers
  - find_thirdparty       : rechercher un tiers (email / nom)
  - get_thirdparty        : lire un tiers par ID
  - list_thirdparties     : lister les tiers
  - create_thirdparty     : créer un nouveau tiers
  - update_thirdparty     : modifier un tiers existant

  Devis
  - get_proposal          : lire un devis par référence (ex: PRO2025-0042)
  - list_proposals        : lister les devis (filtres optionnels)
  - create_proposal       : créer un nouveau devis
  - add_proposal_line     : ajouter une ligne à un devis
  - update_proposal_line  : modifier une ligne d'un devis
  - validate_proposal     : valider un devis (brouillon → validé)
  - close_proposal        : clôturer un devis (signé / non signé)

  Commandes
  - get_order             : lire une commande par référence (ex: CO2025-0012)
  - list_orders           : lister les commandes client
  - create_order          : créer une commande depuis un devis
  - validate_order        : valider une commande

  Factures
  - get_invoice           : lire une facture par référence (ex: FA2025-0042)
  - list_invoices         : lister les factures (filtres : tiers, statut, période)
  - get_invoice_payments  : paiements reçus pour une facture

  Bons de livraison
  - get_shipment          : lire un bon de livraison par ID
  - list_shipments        : lister les bons de livraison

  Produits
  - list_products         : lister les produits/services

  Notes & champs libres
  - add_thirdparty_note   : ajouter/remplacer la note interne d'un tiers
  - update_thirdparty_array_options : mettre à jour les champs extrafields d'un tiers
  - add_proposal_note     : ajouter/remplacer la note interne d'un devis
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


def _post(path: str, body: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    resp = httpx.post(url, headers={**HEADERS, "Content-Type": "application/json"}, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _put(path: str, body: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    resp = httpx.put(url, headers={**HEADERS, "Content-Type": "application/json"}, json=body, timeout=30)
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


# ── Outils écriture Tiers ────────────────────────────────────────────────────

@mcp.tool()
def create_thirdparty(
    name: str,
    email: str = "",
    phone: str = "",
    phone_mobile: str = "",
    fax: str = "",
    address: str = "",
    zip: str = "",
    town: str = "",
    country_id: int = 1,
    state_id: int = 0,
    url: str = "",
    siret: str = "",
    siren: str = "",
    tva_intra: str = "",
    idprof1: str = "",
    idprof2: str = "",
    code_client: str = "",
    code_fournisseur: str = "",
    client: int = 1,
    fournisseur: int = 0,
    note_private: str = "",
    note_public: str = "",
    array_options: dict | None = None,
    extra_fields: dict | None = None,
) -> dict:
    """Créer un nouveau tiers dans Dolibarr.

    Args:
        name:             Nom de la société (obligatoire).
        email:            Adresse email.
        phone:            Téléphone fixe.
        phone_mobile:     Téléphone mobile.
        fax:              Fax.
        address:          Adresse postale.
        zip:              Code postal.
        town:             Ville.
        country_id:       ID pays (1 = France).
        state_id:         ID département/région.
        url:              Site web.
        siret:            Numéro SIRET.
        siren:            Numéro SIREN.
        tva_intra:        Numéro TVA intracommunautaire.
        idprof1:          Identifiant professionnel 1.
        idprof2:          Identifiant professionnel 2.
        code_client:      Code client personnalisé.
        code_fournisseur: Code fournisseur personnalisé.
        client:           1 = client, 0 = prospect.
        fournisseur:      1 = fournisseur.
        note_private:     Note interne.
        note_public:      Note publique.
        array_options:    Extrafields Dolibarr, ex: {"options_segment": "luxe"}.
        extra_fields:     Champs supplémentaires quelconques à fusionner dans le body.

    Returns:
        ID du tiers créé (int).
    """
    body: dict = {
        "name": name,
        "email": email,
        "phone": phone,
        "phone_mobile": phone_mobile,
        "fax": fax,
        "address": address,
        "zip": zip,
        "town": town,
        "country_id": country_id,
        "client": client,
        "fournisseur": fournisseur,
        "note_private": note_private,
        "note_public": note_public,
    }
    if state_id:
        body["state_id"] = state_id
    if url:
        body["url"] = url
    if siret:
        body["idprof2"] = siret
    if siren:
        body["idprof1"] = siren
    if tva_intra:
        body["tva_intra"] = tva_intra
    if idprof1:
        body["idprof1"] = idprof1
    if idprof2:
        body["idprof2"] = idprof2
    if code_client:
        body["code_client"] = code_client
    if code_fournisseur:
        body["code_fournisseur"] = code_fournisseur
    if array_options:
        body["array_options"] = array_options
    if extra_fields:
        body.update(extra_fields)
    return _post("thirdparties", body)


@mcp.tool()
def update_thirdparty(thirdparty_id: int, fields: dict) -> dict:
    """Modifier un tiers Dolibarr existant.

    Args:
        thirdparty_id: ID du tiers à modifier.
        fields:        Dictionnaire des champs à mettre à jour,
                       ex: {"email": "new@mail.com", "phone": "0600000000"}.

    Returns:
        L'objet tiers mis à jour.
    """
    return _put(f"thirdparties/{thirdparty_id}", fields)


@mcp.tool()
def add_thirdparty_note(thirdparty_id: int, note: str, append: bool = True) -> dict:
    """Ajouter ou remplacer la note interne d'un tiers.

    Args:
        thirdparty_id: ID du tiers.
        note:          Texte à ajouter/écrire.
        append:        True = ajouter à la note existante, False = remplacer.

    Returns:
        L'objet tiers mis à jour.
    """
    if append:
        existing = _get(f"thirdparties/{thirdparty_id}")
        existing_note = existing.get("note_private") or ""
        note = f"{existing_note}\n{note}".strip()
    return _put(f"thirdparties/{thirdparty_id}", {"note_private": note})


@mcp.tool()
def update_thirdparty_array_options(thirdparty_id: int, array_options: dict) -> dict:
    """Mettre à jour les champs extrafields (array_options) d'un tiers.

    Args:
        thirdparty_id:  ID du tiers.
        array_options:  Dict des extrafields à modifier,
                        ex: {"options_segment": "luxe", "options_source": "email"}.

    Returns:
        L'objet tiers mis à jour.
    """
    return _put(f"thirdparties/{thirdparty_id}", {"array_options": array_options})


# ── Outils écriture Devis ────────────────────────────────────────────────────

@mcp.tool()
def create_proposal(
    thirdparty_id: int,
    title: str = "",
    note_private: str = "",
    note_public: str = "",
    date_end: str = "",
    date_proposal: str = "",
    mode_reglement_id: int = 0,
    cond_reglement_id: int = 0,
    shipping_method_id: int = 0,
    contact_id: int = 0,
    project_id: int = 0,
    array_options: dict | None = None,
    extra_fields: dict | None = None,
) -> dict:
    """Créer un nouveau devis (brouillon) dans Dolibarr.

    Args:
        thirdparty_id:       ID du tiers client (obligatoire).
        title:               Titre/objet du devis.
        note_private:        Note interne (non visible client).
        note_public:         Note publique (visible sur le PDF).
        date_end:            Date de validité au format YYYY-MM-DD.
        date_proposal:       Date du devis au format YYYY-MM-DD (défaut = aujourd'hui).
        mode_reglement_id:   ID mode de règlement (CB, virement…).
        cond_reglement_id:   ID conditions de règlement (30j, comptant…).
        shipping_method_id:  ID méthode d'expédition.
        contact_id:          ID contact lié au devis.
        project_id:          ID projet Dolibarr associé.
        array_options:       Extrafields Dolibarr, ex: {"options_source": "email"}.
        extra_fields:        Champs supplémentaires quelconques à fusionner dans le body.

    Returns:
        ID du devis créé (int).
    """
    body: dict = {"socid": thirdparty_id}
    if title:
        body["title"] = title
    if note_private:
        body["note_private"] = note_private
    if note_public:
        body["note_public"] = note_public
    if date_end:
        body["fin_validite"] = date_end
    if date_proposal:
        body["date"] = date_proposal
    if mode_reglement_id:
        body["mode_reglement_id"] = mode_reglement_id
    if cond_reglement_id:
        body["cond_reglement_id"] = cond_reglement_id
    if shipping_method_id:
        body["shipping_method_id"] = shipping_method_id
    if contact_id:
        body["contact_id"] = contact_id
    if project_id:
        body["fk_project"] = project_id
    if array_options:
        body["array_options"] = array_options
    if extra_fields:
        body.update(extra_fields)
    return _post("proposals", body)


@mcp.tool()
def add_proposal_line(
    proposal_id: int,
    description: str,
    unit_price: float,
    qty: float = 1.0,
    tva_tx: float = 20.0,
    product_id: int = 0,
    product_type: int = 0,
    remise_percent: float = 0.0,
    date_start: str = "",
    date_end: str = "",
    unit: str = "",
    rang: int = 0,
    special_code: int = 0,
    array_options: dict | None = None,
    extra_fields: dict | None = None,
) -> dict:
    """Ajouter une ligne à un devis Dolibarr.

    Args:
        proposal_id:    ID numérique du devis.
        description:    Libellé de la ligne.
        unit_price:     Prix unitaire HT.
        qty:            Quantité (défaut 1).
        tva_tx:         Taux de TVA en % (défaut 20.0).
        product_id:     ID produit Dolibarr (0 = ligne libre).
        product_type:   0 = produit, 1 = service.
        remise_percent: Remise en % (ex: 10.0 pour 10%).
        date_start:     Date de début prestation (YYYY-MM-DD).
        date_end:       Date de fin prestation (YYYY-MM-DD).
        unit:           Unité (ex: "ex", "kg", "m²").
        rang:           Ordre de la ligne dans le devis.
        special_code:   Code spécial (0 = normal, 3 = sous-total…).
        array_options:  Extrafields de ligne.
        extra_fields:   Champs supplémentaires quelconques.

    Returns:
        ID de la ligne créée (int).
    """
    body: dict = {
        "desc": description,
        "subprice": unit_price,
        "qty": qty,
        "tva_tx": tva_tx,
        "product_type": product_type,
    }
    if product_id:
        body["fk_product"] = product_id
    if remise_percent:
        body["remise_percent"] = remise_percent
    if date_start:
        body["date_start"] = date_start
    if date_end:
        body["date_end"] = date_end
    if unit:
        body["ref_unit"] = unit
    if rang:
        body["rang"] = rang
    if special_code:
        body["special_code"] = special_code
    if array_options:
        body["array_options"] = array_options
    if extra_fields:
        body.update(extra_fields)
    return _post(f"proposals/{proposal_id}/lines", body)


@mcp.tool()
def update_proposal_line(proposal_id: int, line_id: int, fields: dict) -> dict:
    """Modifier une ligne existante d'un devis.

    Args:
        proposal_id: ID numérique du devis.
        line_id:     ID de la ligne à modifier.
        fields:      Champs à modifier, ex: {"qty": 500, "subprice": 1.25}.

    Returns:
        L'objet ligne mis à jour.
    """
    return _put(f"proposals/{proposal_id}/lines/{line_id}", fields)


@mcp.tool()
def validate_proposal(proposal_id: int) -> dict:
    """Valider un devis Dolibarr (brouillon → validé).

    Args:
        proposal_id: ID numérique du devis.

    Returns:
        Résultat de la validation.
    """
    return _post(f"proposals/{proposal_id}/validate", {})


@mcp.tool()
def close_proposal(proposal_id: int, status: int) -> dict:
    """Clôturer un devis (signé ou refusé).

    Args:
        proposal_id: ID numérique du devis.
        status:      1 = signé (gagné), 2 = non signé (perdu).

    Returns:
        Résultat de la clôture.
    """
    return _post(f"proposals/{proposal_id}/close", {"status": status})


@mcp.tool()
def add_proposal_note(proposal_id: int, note: str, public: bool = False, append: bool = True) -> dict:
    """Ajouter ou remplacer la note d'un devis.

    Args:
        proposal_id: ID numérique du devis.
        note:        Texte à écrire.
        public:      False = note interne, True = note publique (visible PDF).
        append:      True = ajouter à la note existante, False = remplacer.

    Returns:
        L'objet devis mis à jour.
    """
    field = "note_public" if public else "note_private"
    if append:
        existing = _get(f"proposals/{proposal_id}")
        existing_note = existing.get(field) or ""
        note = f"{existing_note}\n{note}".strip()
    return _put(f"proposals/{proposal_id}", {field: note})


# ── Outils écriture Commandes ────────────────────────────────────────────────

@mcp.tool()
def create_order_from_proposal(proposal_id: int) -> dict:
    """Créer une commande Dolibarr depuis un devis signé.

    Args:
        proposal_id: ID numérique du devis source.

    Returns:
        ID de la commande créée (int).
    """
    return _post(f"proposals/{proposal_id}/createOrder", {})


@mcp.tool()
def validate_order(order_id: int) -> dict:
    """Valider une commande Dolibarr (brouillon → validée).

    Args:
        order_id: ID numérique de la commande.

    Returns:
        Résultat de la validation.
    """
    return _post(f"orders/{order_id}/validate", {})


# ── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
